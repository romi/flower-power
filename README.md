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


To download the history file, run the following:


    python3 flower-power-history.py <mac-address> <output-file>

It happens that the connection is interrupted before the file transfer
starts. If it does, just launch the command a second time (or
third time...).

