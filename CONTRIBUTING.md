Want to contribute? Great! First, read this page (including the small print at the end).

## Before you contribute
Before we can use your code, you must sign the
[Google Individual Contributor License Agreement]
(https://cla.developers.google.com/about/google-individual)
(CLA), which you can do online. The CLA is necessary mainly because you own the
copyright to your changes, even after your contribution becomes part of our
codebase, so we need your permission to use and distribute your code. We also
need to be sure of various other things—for instance that you'll tell us if you
know that your code infringes on other people's patents. You don't have to sign
the CLA until after you've submitted your code for review and a member has
approved it, but you must do it before we can put your code into our codebase.
Before you start working on a larger contribution, you should get in touch with
us first through the issue tracker with your idea so that we can help out and
possibly guide you. Coordinating up front makes it much easier to avoid
frustration later on.

## Code reviews
All submissions, including submissions by project members, require review. We
use Github pull requests for this purpose. See below for details.

## The small print
Contributions made by corporations are covered by a different agreement than
the one above, the
[Software Grant and Corporate Contributor License Agreement]
(https://cla.developers.google.com/about/google-corporate).

## Creating Issues

* Like many open source projects, we strongly urge you to search through the existing issues before
  creating a new one.
* Please include as many details as possible.
    * Note that this specification's user base are the states and jurisdictions and its primary use
      case is to export structured civics data out of the existing civics management systems.
* All issues should be filed under the milestone "Up for Discussion" until the team moves it under
  a particular release or other related issue-management action.

## Pull Requests

1. Create a branch to work on a fix/feature (a fix/feature should have a companion bug/enhancement
   issue). Start the branch with either "feature/..." or "bug/...".
    1. If you're not a member of the Google team, fork the repository and follow the same
       process.
2. Before sending out a pull request, please make sure that:
    1. if working on a schema bug/feature, the resulting XSD and sample feed XML still validate
        1. You can use http://www.utilities-online.info/xsdvalidation/ to do this validation online, or
        2. If you have the [xmllint](http://xmlsoft.org/xmllint.html) tool installed, please run
           `xmllint --nonet --xinclude --noout --schema civics_cdf_spec.xsd pre_election_sample_feed.xml`
        3. If you have the [Jing](http://www.thaiopensource.com/relaxng/jing.html) validator
           installed, please run `jing civics_cdf_spec.xsd pre_election_sample_feed.xml`
3. Once it's done and tested, create a pull request to move it into the current working branch.
4. At that point, some discussion might happen. In order to get approval for the
   pull request, you will need approval from one representative from Google
   (Google employees still need one approver and cannot self-approve). However
   it is important to note that other members have substantial technical and
   election background as well, so please take all feedback to heart, regardless
   of the source.
    1. Google approvers: @miano @jdmgoogle
5. When it's reviewed and accepted by the team within a reasonable timeframe (TBD), it's merged
   into the current working branch by the developer who created the pull-request.
6. Delete the feature/bug branch.
