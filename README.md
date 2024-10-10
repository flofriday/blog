# blog

My personal blog build with my custom static site generator.

## Usage

First you need to install all requirements with:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```bash
python hellfire.py build .
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

The generator currently is a sinlge script called `hellfire` and uses a custom
Markdown parser.

The each blog post is a directory in the `posts` directory. There all images,
and text, or notes the post uses are bundled together.

## Contribution

Feel free to create an issue or PR if you think I got something wrong or that
a section wasn't understandable.
