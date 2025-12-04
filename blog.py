import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
from textwrap import dedent
import time
from typing import Optional, Self
from meltdown import MarkdownParser, HtmlProducer
from meltdown.Nodes import CodeBlockNode, CommentNode
import os
import re
import shutil

from jinja2 import Template, select_autoescape
import toml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DATE_FORMAT = "%d %b, %Y"


def verify_setup(src: str, dst: str):
    # Verify the source directory is in good health
    if not os.path.isdir(src):
        raise Exception(f"The source directory `{src}` doesn't exist")

    required_files = map(
        lambda f: os.path.join(src, f),
        ["config.toml", "home.template", "post.template"],
    )
    had_error = False
    for file in required_files:
        if not os.path.exists(file):
            print(f"🔥 Required file '{file}' does not exist.")

    if had_error:
        exit(1)

    # Verify the output directory
    if not os.path.isdir(dst):
        os.mkdir(dst)


def load_config(args: dict[str, any]) -> dict:
    config_path = os.path.join(args.source, "config.toml")
    if not os.path.isfile(config_path):
        print(f"🔥 Config '{config_path}' doesn't exist.")
        exit(1)

    config = toml.load(config_path)
    if "url" not in config:
        print(f"🔥 'url' key not found in '{config_path}'")
        exit(1)

    config["show-draft"] = args.show_draft

    return config


# This functions checks if a file already exists and is up to date.
# If any of the sources was updated the destination also needs to be updated
def is_done(dst: str, *srcs: list[str]):
    if not os.path.exists(dst):
        return False

    dst_mtime = os.path.getmtime(dst)
    for src in srcs:
        src_mtime = os.path.getmtime(src)
        if dst_mtime < src_mtime:
            return False

    return True


# Copies all files (shallow copy) from the src to the dst, excluding the
# ignore list.
# Also deletes files that are no longer used.
def copy_files(src: str, dst: str, ignore: Optional[list[str]] = None):
    if ignore is None:
        ignore = []

    old_files = [f for f in os.listdir(dst) if os.path.isfile(os.path.join(dst, f))]
    new_files = [
        f
        for f in os.listdir(src)
        if f not in ignore and os.path.isfile(os.path.join(src, f))
    ]

    # Remove all deleted files
    for dead_file in [
        f
        for f in old_files
        if (f not in new_files and f not in ["index.html", "rss.xml"])
    ]:
        print("Remove: ", os.path.join(dst, dead_file))
        os.remove(os.path.join(dst, dead_file))

    # Copy all new files
    for file in new_files:
        src_path = os.path.join(src, file)
        dst_path = os.path.join(dst, file)

        if is_done(dst_path, src_path):
            continue

        shutil.copyfile(src_path, dst_path)


@dataclass
class PostMetadata:
    name: str = None
    title: str = None
    date: datetime = None
    is_draft: bool = False
    description: str = None
    image: str = None
    other: dict[str, str] = field(default_factory=dict)


# Formats from an unstructured dictionary to the PostMetadata structure and
# does some data clearance
def load_post_metadata(
    raw_metadata: dict[str, str], post: str, base_url: str
) -> PostMetadata:
    meta = PostMetadata()
    meta.name = post
    other = {}
    for key, value in raw_metadata.items():
        # Store the data
        if key == "date":
            meta.date = datetime.strptime(value, "%Y-%m-%d")
        elif key == "title":
            meta.title = value
        elif key == "description":
            meta.description = value
        elif key == "draft" and value.lower() == "true":
            meta.is_draft = True
        elif key == "image":
            if not value.startswith("https://"):
                value = base_url + f"/posts/{post}/{value}"
            meta.image = value
        else:
            other[key] = value

    # Fill in the blanks with warnings
    if meta.title is None or meta.title.strip() == "":
        # TODO: take the filename
        meta.title = "No title available"
        print(f"⚠️ Post '{post}' doesn't have a title in the metadata.")

    if meta.date is None:
        meta.date = datetime.fromtimestamp(os.path.getmtime(post))
        print(f"⚠️ Post '{post}' doesn't have a date in the metadata.")

    if meta.description is None:
        # TODO: We could parse the text and add the start of the post by default
        meta.description = ""
        print(f"⚠️ Post '{post}' doesn't have a description in the metadata.")

    if meta.image is None or meta.image.strip() == "":
        meta.image = base_url + "/flofriday.jpg"

    return meta


def compile_home(src: str, dst: str, config: dict):
    start_time = time.perf_counter()

    @dataclass
    class PostPreview:
        title: str
        description: str
        date: datetime
        url: str

        def date_str(self):
            return datetime.strftime(self.date, DATE_FORMAT)

    template_path = os.path.join(src, "home.template")
    index_path = os.path.join(dst, "index.html")
    rss_template_path = os.path.join(src, "rss.template")
    rss_path = os.path.join(dst, "rss.xml")

    # Iterate over all posts and create a list to which we can link.
    posts = os.listdir(os.path.join(src, "posts"))
    posts = filter(lambda p: os.path.isdir(os.path.join(src, "posts", p)), posts)

    previews = []
    for post in posts:
        # Load the metadata and don't show drafts at the homepage.
        with open(os.path.join(src, "posts", post, "post.md")) as f:
            doc = MarkdownParser().parse(f.read())
        meta = load_post_metadata(doc.metadata, post, config["url"])
        if meta.is_draft is True and not config["show-draft"]:
            continue

        # Map metadata to a post preview
        preview = PostPreview(
            meta.title, meta.description, meta.date, "posts/" + post + "/"
        )
        previews.append(preview)

    previews.sort(key=lambda p: p.date, reverse=True)

    with open(template_path) as home:
        template = Template(
            home.read(),
            autoescape=select_autoescape(
                enabled_extensions=("html", "xml"),
                default_for_string=True,
            ),
        )

    with open(index_path, "w") as index:
        index.write(template.render(previews=previews))

    # Also copy all static files that are not templates into the root of the dst
    copy_files(os.path.join(src, "static"), dst)

    with open(rss_template_path) as rss:
        template = Template(
            rss.read(),
            autoescape=select_autoescape(
                enabled_extensions=("xml"),
                default_for_string=True,
            ),
        )

    with open(rss_path, "w") as index:
        index.write(
            template.render(
                previews=previews, last_build_date=datetime.now(timezone.utc)
            )
        )

    print(f"\tBuilt home in {(time.perf_counter() - start_time) * 1000:.0f}ms")


class CustomHtmlProducer(HtmlProducer):
    def visit_code_block(self: Self, node: CodeBlockNode):
        self._output += "<pre"
        if node.language is not None:
            self._output += f' class="language-{node.language}"'
        self._output += "><code>"
        self._output += html.escape(node.code)
        self._output += "</code></pre>\n"

    def visit_comment(self: Self, node: CommentNode):
        # Skip comments on blog posts
        return


def compile_post(post: str, template: Template, src: str, dst: str, config: dict):
    start_time = time.perf_counter()

    # Also copy all files from the dir to dst
    post_dir = os.path.join(src, "posts", post)
    html_dir = os.path.join(dst, "posts", post)
    post_path = os.path.join(post_dir, "post.md")
    html_path = os.path.join(html_dir, "index.html")
    template_path = os.path.join(src, "post.template")

    if not os.path.isdir(html_dir):
        os.mkdir(html_dir)
    copy_files(post_dir, html_dir, ignore=["post.md"])

    # Skip html if already up to date (this is expensive)
    name = post_path.split("/")[-2]
    if is_done(html_path, post_path, template_path):
        print(
            f"\tBuilt {name} (cached) in {(time.perf_counter() - start_time) * 1000:.0f}ms"
        )
        return

    # Compile the markdown to html
    with open(post_path) as f:
        doc = MarkdownParser().parse(f.read())
    html = CustomHtmlProducer().produce(doc)

    # Write the complete document
    meta = load_post_metadata(doc.metadata, post, config["url"])
    with open(html_path, "w") as f:
        f.write(
            template.render(
                content=html,
                title=meta.title,
                description=meta.description,
                image=meta.image,
                is_draft=meta.is_draft,
                date=datetime.strftime(meta.date, DATE_FORMAT),
            )
        )

    print(f"\tBuilt {name} in {(time.perf_counter() - start_time) * 1000:.0f}ms")


def compile_posts(src: str, dst: str, config: dict):
    dst_path = os.path.join(dst, "posts")
    if not os.path.isdir(dst_path):
        os.mkdir(dst_path)

    template_path = os.path.join(src, "post.template")
    with open(template_path) as home:
        template = Template(
            home.read(),
            autoescape=select_autoescape(
                enabled_extensions=("html", "xml"),
                default_for_string=True,
            ),
        )

    posts = os.listdir(os.path.join(src, "posts"))
    posts = filter(lambda p: os.path.isdir(os.path.join(src, "posts", p)), posts)
    for post in posts:
        compile_post(post, template, src, dst, config)


def build(args):
    start_time = time.perf_counter()
    print("Building Webpage:")

    # Delete everything in a clean build
    if args.clean and os.path.exists(args.out):
        shutil.rmtree(args.out)

    # Setup and verify the conditions
    verify_setup(args.source, args.out)

    # Load the config.toml file
    config = load_config(args)

    # Compile all posts
    compile_posts(args.source, args.out, config)

    # Compile the homepage
    compile_home(args.source, args.out, config)

    print(f"Build complete in {(time.perf_counter() - start_time) * 1000:.0f}ms ✨")


def serve(args):
    if args.clean:
        # FIXME: this traps the builder in an infinite loop of rebuilding
        print("🔥 There is  currently a bug making serve with --clean impossible!")
        exit(1)

    build(args)
    print(
        "\n"
        "🚀 Development server started on http://localhost:8000\n"
        "WARNING: Do not use this in production! 🔥\n"
    )

    # Start the File Watcher

    class BuildHandler(FileSystemEventHandler):
        @staticmethod
        def on_any_event(event):
            # Skip changes in output directory
            if os.path.abspath(event.src_path).startswith(os.path.abspath(args.out)):
                return

            build(args)

    observer = Observer()
    observer.schedule(BuildHandler(), path=args.source, recursive=True)
    observer.start()

    # Start the webserver
    serve_folder = args.out

    class RequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, directory=serve_folder)

        def _should_inject(self):
            return self.path.endswith("/")

        def send_header(self, keyword, value):
            # Don't write content length header for injected documents since we
            # don't want to recalculate the size of the injection and the
            # default server would set the size without the injection which will
            # break Chrome and Safari.
            if self._should_inject() and keyword == "Content-Length":
                return

            return super().send_header(keyword, value)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            return super().end_headers()

        def do_GET(self):
            """Serve a GET request."""
            if not self._should_inject():
                return super().do_GET()

            f = self.send_head()
            if f:
                try:
                    injection = dedent("""
                    <script>
                    let lastContentDate = null;

                    async function checkForUpdates() {
                        try {
                            const response = await fetch(window.location.href, {
                                method: "HEAD",
                                cache: 'no-cache'
                            });
                            const newContentDate = await response.headers.get("last-modified");
                            if (lastContentDate === null) {
                                lastContentDate = newContentDate
                                return
                            }
                            
                            console.log(lastContentDate, newContentDate)
                            if (newContentDate !== lastContentDate) {
                                const response = await fetch(window.location.href, {
                                    cache: 'no-cache'
                                });
                                document.documentElement.innerHTML = await response.text();
                                lastContentDate = newContentDate;
                                hljs.highlightAll();
                            }
                        } catch (error) {
                            console.error('Failed to check for updates:', error);
                        }
                    }

                    setInterval(checkForUpdates, 250);
                    </script>
                    """)

                    text: str = f.read().decode()
                    text = text.replace("</body>", injection + "</body>")
                    patched = BytesIO(text.encode())
                    self.copyfile(patched, self.wfile)
                finally:
                    f.close()

    server_address = ("localhost", 8000)
    httpd = HTTPServer(server_address, RequestHandler)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def new_post(args):
    # Create all used variables
    title = args.title
    date = datetime.now().strftime("%Y-%m-%d")
    whitespace_pattern = re.compile(r"(\s|-)+")
    path_pattern = re.compile(r"[^a-zA-Z0-9\-]+")
    title_path = whitespace_pattern.sub("-", title)
    title_path = path_pattern.sub("", title_path)
    title_path = title_path.lower()

    # Create the directory
    dir_path = os.path.join(args.source, "posts", title_path)
    try:
        os.mkdir(dir_path)
    except FileExistsError as e:
        print(f'🔥 Folder with the name "{e.filename}" already exists.')
        exit(1)

    with open(os.path.join(dir_path, "post.md"), "w") as f:

        def strip_dedent(s: str):
            return dedent(s).strip()

        f.write(
            strip_dedent(
                f"""
                ---
                title: {title}
                date: {date}
                image: some_image_for_social_preview.png
                description: This is just a new post.
                draft: true
                ---

                <!-- Start writing your markdown here ;) -->
                """
            )
        )


def main():
    # Parse the arguments
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build the website.")
    build_parser.add_argument(
        "source", default=".", nargs="?", help="The source directory of the blog."
    )
    build_parser.add_argument(
        "--out", default="./dist", help="The directory to store the generated pages in."
    )
    build_parser.add_argument(
        "--clean",
        action="store_true",
        help="Make a clean build (slow), however it will ensure that no old artifacts will leak.",
    )
    build_parser.add_argument(
        "--show-draft",
        action="store_true",
        help="Show drafts on the homepage.",
    )

    server_parser = subparsers.add_parser(
        "serve",
        help="A development server that, watches the input folder, rebuilds it and serves with it hot-code-reloading.",
    )
    server_parser.add_argument(
        "source", default=".", nargs="?", help="The source directory of the blog."
    )
    server_parser.add_argument(
        "--out", default="./dist", help="The directory to store the generated pages in."
    )
    server_parser.add_argument(
        "--clean",
        action="store_true",
        help="Make a clean build (slow), however it will ensure that no old artifacts will leak.",
    )
    server_parser.add_argument(
        "--show-draft",
        action="store_true",
        help="Show drafts on the homepage.",
    )

    new_parser = subparsers.add_parser("new", help="Create a new post.")
    new_parser.add_argument("title", help="The title of the new post.")
    new_parser.add_argument(
        "source", default=".", nargs="?", help="The source directory of the blog."
    )

    args = parser.parse_args()

    if args.command == "build":
        build(args)
    elif args.command == "serve":
        serve(args)
    elif args.command == "new":
        new_post(args)


if __name__ == "__main__":
    main()
