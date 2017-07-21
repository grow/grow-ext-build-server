# grow-ext-build-server

[![Build
Status](https://travis-ci.org/grow/grow-ext-build-server.svg?branch=master)](https://travis-ci.org/grow/grow-ext-build-server)

A simple server designed to serve Grow-built static websites.

## Features

- Locale-based redirects (`/foo/ -> /en/foo/`).
- Trailing-slash redirects (`/foo -> /foo/`).
- Custom error pages.
- Zero-configuration full-text search service with Google App Engine.

## Usage

### Initial setup

1. Create an `extensions.txt` file within your pod.
1. Add to the file: `git+git://github.com/grow/grow-ext-build-server`
1. Run `grow install`.

### Google App Engine deployment

Use an `app.yaml` file like the one below.

```
# Default app.yaml.

api_version: 1
runtime: python27
threadsafe: true

handlers:
- url: /_grow/cron.*
  script: extensions.grow_build_server.cron
  secure: always
  login: admin
- url: /_grow/api.*
  script: extensions.grow_build_server.api
  secure: always
- url: /.*
  script: extensions.grow_build_server.app
  secure: always
 
skip_files:
- (?!(build|extensions|podspec.yaml).*)
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

### Localization

Let's review what happens when a user makes a request:

1. User requests `/foo/`.
1. The server uses the `X-AppEngine-Country` header to determine the country
   of the user. In this example, let's say the country is `JP`.
1. The server looks for a file at `/ja_jp/foo/index.html`.
1. If the file exists, the server redirects the user to `/ja_jp/foo/`.
1. If the file doesn't exist (in other words, if we don't have a localized
   `/foo/`), it serves the file at `/foo/index.html` instead.

### Full-text search

You can provide your users with full-text search of your site's content using
this extension. Here's how it works:

1. When the application is deployed, a background task kicks off to index (or
   reindex) your site's content. This task only runs once per deployment.
1. The application exposes a JSON-based API (via `ProtoRPC`) for creating a
   client-side search experience in your site.

To search, make a request like...

```
POST /_grow/api/search
Content-Type: application/json

{
    "query": {
        "q": <query string>,
        "cursor": <cursor>, (optional)
        "limit": <limit> (optional)
    }
}
```

... which sends a response like:

```
{
    "documents: [
        "document": {
            "title": <page title>,
            "path": <url path>,
        },
        ...
    ],
    "cursor": <cursor>
}
```

## Extending it

This extension is implemented as a standard `WSGI` application, so you may
compose it into your own Python-based server as you like.

## TODO

- Only `/{locale}/{path}/` URL formats are supported.
- Deterministic behavior for multi-language territories. 
