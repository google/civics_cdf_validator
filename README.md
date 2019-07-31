`election_results_xml_validator` is a script that checks if a NIST 1500-100
data feed follows best practices. It will output errors, warnings, and info
messages for common issues.

This is not an official Google product.

# INSTALLATION

The package is available from PyPi and can be installed using the command
below.

  ```pip install election_results_xml_validator```

election_results_xml_validator relies on lxml which will be installed if it
isn't already installed. You may need to install libxslt development libraries
in order to build lxml.


# USAGE

## List rules

You can list the validation rules that the script contains and the description
of each rule by running the following command

```
election_results_xml_validator list
```

## Validate a file

The validate command has 2 required arguments:

  * the election file to be validated
  * the XSD file to validate against

The command to validate the election file against all the rules in the file is

```
election_results_xml_validator validate election_file.xml --xsd election_data_spec.xsd
```

The validator is capable of validating either election or officeholder data
feeds, depending on the value of the `--rule_set` flag (`election` is the
default). To validate an officeholder feed:

```
election_results_xml_validator validate election_file.xml --xsd election_data_spec.xsd --rule_set officeholder
```

One can choose to only validate one or more comma separated rules by using the `-i` flag

```
election_results_xml_validator validate election_file.xml --xsd election_data_spec.xsd -i Schema
```

Or choose to exclude one or more comma separated rules using the `-e` flag

```
election_results_xml_validator validate election_file.xml --xsd election_data_spec.xsd -e Schema
```

By default, the script only shows a summary of issues found. You can get a
verbose report by adding the `-v` flag

```
election_results_xml_validator validate election_file.xml --xsd election_data_spec.xsd -v
```
