# grow-ext-build-server

[![Build
Status](https://travis-ci.org/grow/grow-ext-build-server.svg?branch=master)](https://travis-ci.org/grow/grow-ext-build-server)

A simple server designed to serve Grow-built static websites.

## Concept

(WIP)

- Implements a locale-based redirect to serve localized content.
- Uses `podspec.yaml` to validate locales.
- Supports serving a 404 page.

## Usage

### Initial setup

1. Create an `extensions.txt` file within your pod.
1. Add to the file: `git+git://github.com/grow/grow-ext-build-server`
1. Run `grow install`.

This extension also implements a standard `WSGIApplication`, so you may compose
your own Python-based server as you like.

### Google App Engine deployment

Use an `app.yaml` file like the one below.

```
# Default app.yaml.

runtime: python27
api_version: 1
threadsafe: true

handlers:
- url: /.*
  script: extensions.grow_build_server.app
```
