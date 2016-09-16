election_results_xml_validator is a script that checks if a NIST 1500-100
election results feed follows best practices and outputs errors, warnings and
info messages for common issues

This is not an official Google product.

INSTALLATION
------------

The package is avaiable from PyPi and can be installed using the command
below.

pip install election_results_xml_validator

election_results_xml_validator relies on lxml which will be installed if it
isn't already installed. You may need to install libxslt development libraries
in order to build lxml.


USAGE
-----

1. List rules

  You can list the validation rules that the script contains and the description
  of each rule by running the following command

  election_results_xml_validator list

2. Validate a file

  The validate command has 2 required arguments
    * the election file to be validated
    * the NIST XSD file to validate against

The command to validate the election file against all the rules in the file is

```election_results_xml_validator validate election_file.xml --xsd nist.xsd```

You can choose to only check one rule by using the -i flag

```election_results_xml_validator validate election_file.xml --xsd nist.xsd -i Schema```

Or choose to exclude a rule using the -e flag

```election_results_xml_validator check election_file.xml --xsd nist.xsd -e Schema```

By default, the script only shows a summary of issues found. You can get a
detailed report by adding the -d flag

```election_results_xml_validator check election_file.xml --xsd nist.xsd -d```
