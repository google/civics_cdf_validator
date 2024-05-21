`civics_cdf_validator` is a script that checks if a NIST 1500-100
data feed follows best practices. It will output errors, warnings, and info
messages for common issues.

This is not an official Google product.

# INSTALLATION

The package is available from PyPi and can be installed using the command
below.

  ```pip install civics_cdf_validator```

civics_cdf_validator relies on lxml which will be installed if it
isn't already installed. You may need to install libxslt development libraries
in order to build lxml.


# USAGE

## Branch Definitions
* `master` - Branch used in production.
* `staging` - Branch that contains next version of production code, typically available one month in advance of a production push.
* `dev` - Branch that contains development code with latest changes changes to the validator. This branch is rolled into staging on a monthly basis.


## Supported feeds
You can use `civics_cdf_validator` to check different types of feed:

* Officeholder
* Candidate
* Results
* Committee
* Election Dates
* Metadata

## List rules

You can list the default validation rules attached with a brief description of
each by using the "list" command:

```
civics_cdf_validator list
```

You can also customize the displayed list by specifying your set of rules or at
least you can filter the default list using parameters as the feed type / ignore
rules flag.

For more details, you can use the command help :

```
civics_cdf_validator list --help
```

## Validate a file

The validate command has 2 required arguments:

  * the election file to be validated
  * the XSD file to validate against

The command to validate the election file against all the rules in the file is

```
civics_cdf_validator validate election_file.xml --xsd civics_cdf_spec.xsd
```

The validator is capable of validating either election or officeholder data
feeds, depending on the value of the `--rule_set` flag (`election` is the
default). Examples:

  * Validate an officeholder feed:

  ```
  civics_cdf_validator validate officeholder_file.xml --xsd civics_cdf_spec.xsd --rule_set officeholder
  ```

  * Validate a results feed:

  ```
  civics_cdf_validator validate results_file.xml --xsd civics_cdf_spec.xsd --rule_set election_results
  ```

  * Validate a metadata feed:

  ```
  civics_cdf_validator validate metadata_file.xml --xsd metadata_spec.xsd --rule_set metadata
  ```

One can choose to only validate one or more comma separated rules by using the `-i` flag

```
civics_cdf_validator validate election_file.xml --xsd civics_cdf_spec.xsd -i Schema
```

Or choose to exclude one or more comma separated rules using the `-e` flag

```
civics_cdf_validator validate election_file.xml --xsd civics_cdf_spec.xsd -e Schema
```

By default, the script only shows a summary of issues found. You can get a
verbose report by adding the `-v` flag

```
civics_cdf_validator validate election_file.xml --xsd civics_cdf_spec.xsd -v
```
