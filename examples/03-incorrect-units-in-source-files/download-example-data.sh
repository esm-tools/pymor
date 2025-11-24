#!/bin/bash -e
#
# Downloads the example data for this example from DRKZ's Swift object storage
#

if [ -d model_runs ]; then
  echo "Example data for $(basename $(pwd)) already downloaded..."
  exit 0
fi

module load py-python-swiftclient
# [FIXME] PG: This needs to get fixed in the swift object storage as well, for now it has the wrong name:
swift download pymorize_demo_data 03-incorrect-units-in-source-files-model-runs.tgz
tar -xzvf 03-incorrect-units-in-source-files-model-runs.tgz
rm 03-incorrect-units-in-source-files-model-runs.tgz
