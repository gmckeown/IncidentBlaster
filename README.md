# Incident Blaster

This script uses the BMC Remedy REST API to generate a specified number of incidents. The field data is chosen randomly from values provided in the configuration files.

## Versions
There are two versions of the script:
- *Python 2*: A version for Python 2 with no dependencies outside of the standard modules. This is the original version of the script and is intended for use in environments where Python 3 is unavailable and/or installing dependencies with pip is difficult.
- *Python 3*: A more streamlined version of the script for Python 3 that requires the Requests module. This version has also factored out much of the Remedy-specific code into an integration module.

## Configuration

- ***RestConfig.json*** contains the target URL and login details.
- ***RuntimeValues.json*** tracks the incident counter and is where you choose the number of incidents to create
- ***StandardConfig.json*** contains the base data that is typically common across installations
- ***CustomerConfig.json*** contains the foundation data that tends to be unique to an installation

For `RestConfig.json`, `CustomerConfig.json` and `RuntimeValues.json`, take copies of the template versions of these files and substitute in your own configuration.

The password should be BASE64 encoded before placing into the REST Config file. There are many online services that can do this, or if you're a little more cautious you can use the following on Linux:
```Bash
echo -n "MyP@ssw0rd" | base64
```

On Windows you can use PowerShell:
```PowerShell
[System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("MyP@ssw0rd"))
```

**NOTE:** To change the fields set on create, currently you'll need to edit the script.

***WARNING:*** You probably want to create one or two incidents at a time into a test environment initially!

## Compatibility
The original script is designed to work with Python 2.7 using only standard modules, since that was what was available in the environment in which it was first needed. The new, primary, version of the script is designed to work with Python 3 and needs a minimum of Python 3.6. This minimum version is driven largely by the use of f-strings in the code. We are also using the `typing` module (needs Python 3.5+), and `pathlib` (needs Python 3.4+).

## Troubleshooting
If you aren't getting the results you expect, set the debug flag in the script to True and that may help identify the problem (yes, command-line argument support for this would be a good idea...).

## Updates and Improvements
All feedback welcome, as well as pull requests for any bug fixes, code improvements, or new features.
