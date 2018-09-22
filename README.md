Signingscript
==============

[![Build Status](https://travis-ci.org/mozilla-releng/signingscript.svg?branch=master)](https://travis-ci.org/mozilla-releng/signingscript) [![Coverage Status](https://coveralls.io/repos/github/mozilla-releng/signingscript/badge.svg?branch=master)](https://coveralls.io/github/mozilla-releng/signingscript?branch=master)

This is designed to be run from scriptworker, but runs perfectly fine as a standalone script.


Testing
-------

Testing takes a few steps to set up.  Here's how:

### docker-signing-server

To test, you will need to point at a signing server.  Since production signing servers have restricted access and sensitive keys, it's easiest to point at a docker-signing-server instance locally during development.

To do so:

    git clone https://github.com/escapewindow/docker-signing-server
    cd docker-signing-server
    # Follow ./README.md to set up and run the docker instance

Remember the path to `./fake_ca/ca.crt` ; this will be the file that signingscript will use to verify the SSL connection.

### virtualenv

First, you need `python>=3.6.0`.

Next, create a python35 virtualenv, and install signingscript:

    # create the virtualenv in ./venv3
    virtualenv3 venv3
    # activate it
    . venv3/bin/activate
    # install signingscript from pypi
    pip install signingscript

If you want to use local clones of [signingscript](https://github.com/mozilla-releng/signingscript), [signtool](https://github.com/mozilla-releng/signtool), and/or [scriptworker](https://github.com/mozilla-releng/scriptworker), you can

    python setup.py develop

in each of the applicable directories after, or instead of the `pip install` command.

### password yaml

You'll need a password yaml file.  The format is

```yaml
BASE_CERT_SCOPE:dep-signing:
  server-pool-nick:
    urls:
      - IPADDRESS:PORT
      - ...
    formats: ["SIGNING_FORMAT1", "SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: signing-server
  autograph-pool-nick:
    urls:
      - https://HOST:PORT
      - ...
    formats: ["AUTOGRAPH_SIGNING_FORMAT1", "AUTOGRAPH_SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: autograph
BASE_CERT_SCOPE:nightly-signing
  server-pool-nick:
    urls:
      - IPADDRESS:PORT
      - ...
    formats: ["SIGNING_FORMAT1", "SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: signing-server
  autograph-pool-nick:
    urls:
      - https://HOST:PORT
      - ...
    formats: ["AUTOGRAPH_SIGNING_FORMAT1", "AUTOGRAPH_SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: autograph
BASE_CERT_SCOPE:release-signing:
  server-pool-nick:
    urls:
      - IPADDRESS:PORT
      - ...
    formats: ["SIGNING_FORMAT1", "SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: signing-server
  autograph-pool-nick:
    urls:
      - https://HOST:PORT
      - ...
    formats: ["AUTOGRAPH_SIGNING_FORMAT1", "AUTOGRAPH_SIGNING_FORMAT2", ...]
    user: user
    pass: pass
    server-type: autograph
```

This stripped down version will work with docker-signing-server:

```yaml
project:releng:signing:cert:dep-signing:
    docker-signing-server:
        urls:
            - "127.0.0.1:9110"
        formats: ["gpg"]
        user: user
        user: pass
        server-type: signing-server
```

The user/pass for the docker-signing-server are `user` and `pass` for super sekrit security.

### config json

The config json looks like this (comments are not valid json, but I'm inserting comments for clarity.  Don't include the comments in the file!):


    {
      // path to the password json you created above
      "signing_server_config": "/src/signing/signingscript/example_server_config.yaml",

      // the work directory path.  task.json will live here, as well as downloaded binaries
      // this should be an absolute path.
      "work_dir": "/src/signing/work_dir",

      // the artifact directory path.  the signed binaries will be copied here for scriptworker to upload
      // this should be an absolute path.
      "artifact_dir": "/src/signing/artifact_dir",

      // the IP that docker-signing-server thinks you're coming from.
      // I got this value from running `docker network inspect bridge` and using the gateway.
      "my_ip": "172.17.0.1",

      // how many seconds should the signing token be valid for?
      "token_duration_seconds": 1200,

      // the path to the docker-signing-server fake_ca cert that you generated above.
      "ssl_cert": "/src/signing/docker-signing-server/fake_ca/ca.crt",

      // the path to signtool in your virtualenv that you created above
      "signtool": "/src/signing/venv3/bin/signtool",

      // enable debug logging
      "verbose": true,

      // the path to zipalign. This executable is usually present in $ANDROID_SDK_LOCATION/build-tools/$ANDROID_VERSION/zipalign
      "zipalign": "/absolute/path/to/zipalign",

      // The host and port to use when sending metrics to datadog statsd
      // Datadog's default is 8125, ours is 8135 due to a conflict with collectd
      "datadog_port": 8135,
      "datadog_host": "localhost"

    }

#### directories and file naming
If you aren't running through scriptworker, you need to manually create the directories that `work_dir` and `artifact_dir` point to.  It's better to use new directories for these rather than cluttering and potentially overwriting an existing directory.  Once you set up scriptworker, the `work_dir` and `artifact_dir` will be regularly wiped and recreated.

Scriptworker will expect to find a config.json for the scriptworker config, so I name the signingscript config json `script_config.json`.  You can name it whatever you'd like.

### file to sign

Put the file(s) to sign somewhere where they can be reached via the web; you'll point to their URL(s) in the task.json below.  Alternately, point to the artifacts of a TaskCluster task, and add the `taskId` to your `dependencies` in the task.json below.

### task.json

Ordinarily, scriptworker would get the task definition from TaskCluster, and write it to a `task.json` in the `work_dir`.  Since you're initially not going to run through scriptworker, you need to put this file on disk yourself.

It will look like this:

    {
      "created": "2016-05-04T23:15:17.908Z",
      "deadline": "2016-05-05T00:15:17.908Z",
      "dependencies": [
        "VALID_TASK_ID"
      ],
      "expires": "2017-05-05T00:15:17.908Z",
      "extra": {},
      "metadata": {
        "description": "Markdown description of **what** this task does",
        "name": "Example Task",
        "owner": "name@example.com",
        "source": "https://tools.taskcluster.net/task-creator/"
      },
      "payload": {
        "upstreamArtifacts": [{
          "taskId": "upstream-task-id1",
          "taskType": "build",
          "paths": ["public/artifact/path1", "public/artifact/path2"],
          "formats": []
        }],
        "maxRunTime": 600
      },
      "priority": "normal",
      "provisionerId": "test-dummy-provisioner",
      "requires": "all-completed",
      "retries": 0,
      "routes": [],
      "schedulerId": "-",
      "scopes": [
        "project:releng:signing:cert:dep-signing",
        "project:releng:signing:format:gpg"
      ],
      "tags": {},
      "taskGroupId": "CRzxWtujTYa2hOs20evVCA",
      "workerType": "dummy-worker-aki"
    }

The important entries to edit are the `upstreamArtifacts`, the `dependencies`, and the `scopes`.

The `upstreamArtifacts` point to the file(s) to sign.  Because scriptworker downloads and verifies their shas, signingscript expects to find the files under `$work_dir/cot/$upstream_task_id/$path`

The first scope, `project:releng:signing:cert:dep-signing`, matches the scope in your password yaml that you created.  The second scope, `project:releng:signing:format:gpg`, specifies which signing format to use.  (You can specify multiple formats by adding multiple `project:releng:signing:format:` scopes)

Write this to `task.json` in your `work_dir`.

### run

You're ready to run signingscript!

    signingscript CONFIG_FILE

where `CONFIG_FILE` is the config json you created above.

This should download the file(s) specified in the payload, download a token from the docker-signing-server, upload the file(s) to the docker-signing-server to sign, download the signed bits from the docker-signing-server, and then copy the signed bits into the `artifact_dir`.

### troubleshooting

Invalid json is a common error.  Validate your json with this command:

    python -mjson.tool JSON_FILE

Your docker-signing-server shell should be able to read the `signing.log`, which should help troubleshoot.

### running through scriptworker

[Scriptworker](https://github.com/mozilla-releng/scriptworker) can deal with the TaskCluster specific parts, and run signingscript.

Follow the [scriptworker readme](https://github.com/mozilla-releng/scriptworker/blob/master/README.rst) to set up scriptworker, and use `["path/to/signingscript", "path/to/script_config.json"]` as your `task_script`.

Make sure your `work_dir` and `artifact_dir` point to the same directories between the scriptworker config and the signingscript config!
