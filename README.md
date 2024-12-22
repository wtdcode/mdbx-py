# Python bindings for libmdbx

This revives the python bindings for libmdbx.

Originally forked from [libmdbx](https://github.com/erthink/libmdbx/tree/python-bindings) with a few bugs fixed.

Try it with

```bash
pip install libmdbx
```

Contributions and feedbacks are highly welcome. I'm developing a few more pythonic features and adding support for cursors iterating dupsort databases.

## Manual build

Clone the repo

```bash
git clone https://github.com/wtdcode/mdbx-py
git submodule update --init --recursive
```

Install via poetry

```bash
poetry install
```

That's it!