# blog

My personal blog build with my custom static site generator.

## Usage

I use [uv](https://github.com/astral-sh/uv) to manage python and it's dependencies for my personal blog.

Once installed simply run :
```bash
uv run blog.py
```

```
usage: blog.py [-h] {build,serve,new} ...

positional arguments:
  {build,serve,new}
    build            Build the website.
    serve            A development server that, watches the input folder, rebuilds it and serves it on localhost:8000
    new              Create a new post.

options:
  -h, --help         show this help message and exit
```

## Structure

This repository holds all all source code to build my blog and all contents of
each blog.

The generator currently is a single script called `blog.py` and uses a custom
Markdown parser.

Each blog post is a directory in the `posts` directory. There all images,
and text, or notes the post uses are bundled together. Subdirectories will
be ignored.

In the frontmatter of a post the following fields are supported:
- **date:** When the post was published `YYYY-MM-DD`
- **title:** Used for the title and on the homepage
- **description:** Only used for social media previews
- **image:** Only used for social media previews
- **draft:** Whether or not the post is finished (true/false)

Drafts are unfinished posts, and therefore don't appear on the home page listing
(unless `--show-draft` is enabled). However, draft's are always rendered and
deployed so that you can send the link to some friends for proof-reading.

The rationale behind that is that the drafts are anyway public in this repo.

## Contribution

Feel free to create an issue or PR if you think I got something wrong or that
a section wasn't understandable.
