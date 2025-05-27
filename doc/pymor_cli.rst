===========================
Usage: The ``pymor`` CLI
===========================

``pymor`` is the command line interface to the ``pymor`` package. It provides
a simple way to interface with the underlying Python, without needing to know too
many details about what is going on behind the scenes. The CLI is hopefully simple
and is the recommended way to get going.

You can get help with::

  pymor -h

The CLI is divided into a few subcommands. The main one you will want to use is::

  pymor process <configuration_yaml>

This will process the configuration file and run the CMORization process. Read on for
a full summary of the commands.

* ``pymor develop``: Tools for developers

  - Subcommand ``ls``: Lists a directory and stores the output as a ``yaml``. Possibly
    useful for development work and creating in-memory representations of certain folders.

* ``pymor externals``: List external program status

  You might want to use ``NCO`` or ``CDO`` in your workflows. The ``pymor externals`` command
  lists information about the currently found versions for these two programs.

* ``pymor plugins``: Extending the command line interface

  The user can extend the pymor CLI by adding their own plugins to the main command. This
  lists the docstrings of those plugins.

  .. note:: Paul will probably throw this out when we clean up the project for release.

* ``pymor process``: The main command. Takes a yaml file and runs through the CMORization process.

* ``pymor ssh-tunnel``: Creates port forwarding for Dask and Prefect dashboards. You should provide
  your username and the remote **compute** node, **not the login node**. The tunnels will default to ``8787`` for
  Dask and ``4200`` for Prefect.

  .. important:: You need to run this from your laptop!

* ``pymor table-explorer``: Opens up the web-based table explorer. This is a simple way to explore the
  tables that are available in the CMIP6 data request.

* ``pymor validate``: Runs checks on a configuration file.

Command Line Reference
======================

.. click:: pymor.cli:cli
   :prog: pymor
   :nested: full
