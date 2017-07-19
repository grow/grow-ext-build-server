# grow-ext-build-server

[![Build
Status](https://travis-ci.org/grow/grow-ext-build-server.svg?branch=master)](https://travis-ci.org/grow/grow-ext-build-server)

(WIP) A simple server designed to serve Grow-built static websites.

## Concept

- Implements a locale-based redirect to serve localized content.
- Uses `podspec.yaml` to validate locales.
- Supports serving a 404 page.

## Usage

### Initial setup

1. Create an `extensions.txt` file within your pod.
1. Add to the file: `git+git://github.com/grow/grow-ext-build-server`
1. Run `grow install`.

NOTE: This extension also implements a standard `WSGIApplication`, so you may
compose your own Python-based server as you like.

### Google App Engine deployment

Use an `app.yaml` file like the one below.

```
# Default app.yaml.

api_version: 1
runtime: python27
threadsafe: true

handlers:
- url: /.*
  script: extensions.grow_build_server.app
 
skip_files:
- (?!(build|extensions|podspec.yaml).*)
- ^extensions/(?!__init__\.py$|grow_build_server).*
```

## How it works

This extension permits serves your Grow-built website with a little dynamic
functionality. Specifically, it implements territory-based redirects based on
the localization configuration in your `podspec.yaml`. Here's how it works.

1. Install the extension using the setup instructions above.
1. Build normally with `grow build`. This produces a static fileset in the
   `build` directory.
1. Drop an `app.yaml` file in your directory (see example above) and deploy
   with `gcloud app deploy`.

Now you have your static fileset and this extension deployed to Google App
Engine.

Let's review what happens when a user makes a request:

1. User requests `/foo/`.
1. The server uses the `X-AppEngine-Country` header to determine the country
   of the user. In this example, let's say the country is `JP`.
1. The server looks for a file at `/ja_jp/foo/index.html`.
1. If the file exists, the server redirects the user to `/ja_jp/foo/`.
1. If the file doesn't exist (in other words, if we don't have a localized
   `/foo/`), it serves the file at `/foo/index.html` instead.

The server also does a few other things, like an automatic trailing slash
redirect as well as supporting serving a custom 404 page. 

## TODO

- Only `/{locale}/{path}/` URL formats are supported.
- Deterministic behavior for multi-language territories. 
