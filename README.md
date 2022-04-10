# flower-power

This is a Python script to read the history file of the Parrot
FlowerPower sensors and store the data in a JSON file.

It's currently tested only on Linux.

To get this up and running you'll need to install the gatt python package:

https://github.com/getsenic/gatt-python

It has clear documentation on how to install the dependencies.

Before using the script, you have to know the Bluetooth MAC address of
the FlowerPower. There are a number of tools available to scan the
avaiable BLE devices around you.

If you installed gatt-python then you can run the following command:

    gattctl --discover

You may have to run it with super-user privileges.

    sudo gattctl --discover


## Download the history from a single FlowerPower

To download the history file, run the following:


    python3 flower-power-history.py download <mac-address> <output-file>

It happens that the connection is interrupted before the file transfer
starts. If it does, just launch the command a second time (or
third time...).


## Download the history from a list of FlowerPowers

To download the history files of a list of FlowerPowers, you must
prepare a JSON-formatted config file in advance. The file short
contain an array of objects, one per FlowerPower. Each object should
contain an id and address field. The must me an additional 'location'
field. This is an object with an 'id' field. An example is shown below:


    [
        {
            "id": "device1",
            "address": "a0:14:3d:0c:d0:f3",
            "location": {
                "id": "myfarm"
            }
        },
        {
            "id": "device2",
            "address": "a0:14:3d:0c:cb:0d",
            "location": {
                "id": "myfarm"
            }
        }
    ]

Any additional fields are ignored, so you can add more information for
your usage if you want.

To download the history of all devices in the config file, run the
following command:

    python3 flower-power-history.py download-using-config <config-file>

Using the example config file from above, the history will be stored
in a file called 'myfarm-YYYYMMDD-device{1,2}.json', with YYYYMMDD the
current date.

If the output file already exists, the download will be skipped. This
reason is that it is possible to repeat the download several times in
case one of the devices did not complete the operation.

## Merging history files

It's possible to merge two history files with the following command:

    python3 flower-power-history.py merge <file-1> <file-2> <output>

The output file may be the same as one of the input files.
