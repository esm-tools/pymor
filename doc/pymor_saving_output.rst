=============
Saving Output
=============

This section of the documentation shows what control you have over output file generation.

Output Location
---------------

Use the key ``output_directory`` to determine where output will be stored:

.. code-block:: yaml

    rules:
      - ... other rule configuration ..
        output_directory: /some/path/on/the/system
        ... other rule configuration ...
      - ... other rule configuration ..
        output_directory: .  # Relative to the current working path
        ... other rule configuration ...
      - ...another rule...

Frequency Grouping
------------------

In the rule section for a particular output, you can control how many timesteps (expressed in days, months, years, etc)
should be contained in each file. You can use the key ``"output_frequency"``:

.. code-block::  yaml

    rules:
      - ... other rule configuration ...
        output_frequency: 50YE
        ... other rule configuration ...
      - ...another rule...

The full list of possibilities for the frequency strings can be found here: https://pandas.pydata.org/docs/user_guide/timeseries.html#offset-aliases
