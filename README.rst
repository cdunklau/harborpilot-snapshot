HarborPilot
###########

A middleman for building Docker images.


Installation and Startup
========================

.. note:: This is for a development install

1.  Log into the Vagrant VM with ``vagrant ssh``.
2.  Create a virtualenv, and install wheel (for building pyyaml):
    ``python3 -m venv harborpilotenv && harborpilotenv/bin/pip install wheel``.
3.  Install harborpilot as editable:
    ``harborpilotenv/bin/pip install -e /vagrant/harborpilot``.
4.  Create a configuration file at ``harborpilot.conf``, see the next
    section for the format. Using this will allow you to test it with
    the "phraseapi" demo::

        builds:
            # Build name, the part in the URL.
            phraseapi:
                # Docker image name
                image_name: phraseapi_docker_image
                # Docker image tag
                image_tag: latest
                # config for git pulling
                git:
                    # The git remote to pull from
                    remote: /vagrant/
                    # The branch to clone, change this if you're hacking
                    # the demo containers on a branch.
                    branch: master
                    # A relative path inside the git repo
                    # to use as the build context
                    context_relpath: demo-containers/phraseapi

5.  Run the service, sudo because it needs root to talk to Docker:
    ``sudo harborpilotenv/bin/harborpilot``.
6.  Test it out:
    ``curl -v -X POST 'http://127.0.0.1:18080/apis/builds/phraseapi'``.
    Replace the last bit of the URL if you used a different build name.
7.  Make sure the image was created: ``sudo docker image ls``.


Configuration
=============

.. code:: yaml

    # Server listen address. Defaults to 127.0.0.1
    address: 127.0.0.1

    # Server listen port. Defaults to 18080
    port: 18080

    # Mapping of image ref -> image config
    builds:

        # The image ref. This is the thing in the URL.
        my_test_build_name:

            # Docker image name
            image_name: my_test_image

            # Docker image tag. Defaults to latest
            image_tag: latest

            # config for git pulling
            git:

                # The git remote to pull from. Required
                remote: /some/git/remote

                # The branch to clone. Defaults to master
                branch: master

                # A relative path inside the git repo
                # to use as the build context. Defaults to
                # the repository root.
                context_relpath: my_build_context



Permissions
===========

.. note:: This isn't implemented, just a potential idea.

A permission statement is a tuple of (endpoint_pattern, allowed_actions).
The endpoint pattern mirrors the API endpoints without the leading ``/apis/``
component, with wildcard components possible. Examples::

    # Allow POST to the builds endpoint for the image specified by ref "spam".
    ('builds/spam', ('POST',))

    # Allow POST to the builds endpoint for any image.
    ('builds/*', ('POST',))


API Endpoints
=============

``/apis/builds/{build_name}``
+++++++++++++++++++++++++++++

The ``build_name`` is just a string that tells HarborPilot which configuration
to use. The string is nonempty, case insensitive, and contains only ASCII
letters, digits, the underscore, and/or the hyphen (TODO: Add validation for
this).

This can't be the same as Docker's concept of an image name (really repository
name) because things like slash-separation and various indexes make this more
complex than would be reasonable for the simple API this should be.

POSTing to this endpoint tells HarborPilot to pull from the configured repo and
build the Docker image.

Possible response semantics:

-   Respond immediately, no feedback if build was even started, much less
    successful.
-   Respond after HarborPilot gets a successful response from the Docker
    engine, which means Docker has validated the Dockerfile syntax and started
    building the image.
-   Respond after build finishes or errors.
-   Some hybrid of the above. Perhaps let Docker validate Dockerfile syntax
    before responding with 201, and then provide status updates with the
    response body until build succeeds or fails.
