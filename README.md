# Python bindings for libmdbx

This revives the python bindings for libmdbx.

Originally forked from [libmdbx](https://github.com/erthink/libmdbx/tree/python-bindings) with a few bugs fixed.

Try it with

```bash
pip install libmdbx
```

Contributions and feedbacks are highly welcome.

## Usage

A quick sample to read all values from the default database:

```python
with Env(...) as env:
    with env.ro_transaction() as txn:
        with txn.cursor() as cur:
            for k, v in cur.iter():
                ...
```

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