
[View on GitHub](https://github.com/fractalexperience/xbrl)

# xbrl

## A Lightweight XBRL Taxonomy and Instance Document Model

# Taxonomy Browsing Examples

**XBRL Taxonomies** include a large amount of different objects such as **Reporting Concept** definitions (Metrics), **Dimensions** and their **Members**, **Enumerations**, Lexical information in form of **Labels** and **References** to normative documents, semantic information in form of inter\-concept relationships, layout information in form of **Tables**, analytic information in form of **Formulas** etc. {XM} can be used to effectively browse these objects and display them in form of **HTML reports**.

## Example 1 \- Report concepts

Open US\-GAAP 2021 Financial Reporting Taxonomy and create a report of concepts in “srt” namespace. Click [here](/xbrl/us-gaap-2021-concepts-srt.html) to see the result.

```
import os
from xbrl.base import pool
from xbrl.engines import tax_reporter

# US-GAAP taxonomy - version 2021
url = 'https://xbrl.fasb.org/us-gaap/2021/us-gaap-2021-01-31.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
tax = data_pool.add_package(url)
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# List concepts with 'srt' prefix
rep.r_concepts([c for c in tax.concepts.values() if c.prefix == 'srt'])
output_file = os.path.join(data_pool.output_folder, 'us-gaap-2021-concepts-srt.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 2 \- Presentation Hierarchies

Open US\-GAAP 2021 Financial Reporting Taxonomy and list all presentation hierarchies in a HTML table. Click [here](/xbrl/us-gaap-2021-presentations.html) to see the result.

```
import os
from xbrl.base import pool, const
from xbrl.engines import tax_reporter

# US-GAAP taxonomy - version 2021
url = 'https://xbrl.fasb.org/us-gaap/2021/us-gaap-2021-01-31.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
package = data_pool.cache_package(url)
entry_point = 'https://xbrl.fasb.org/us-gaap/2021/entire/us-gaap-entryPoint-all-2021-01-31.xsd'
tax = data_pool.add_taxonomy([entry_point])
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# List presentation hierarchies in a HTML table
rep.r_base_sets('presentationArc', const.PARENT_CHILD_ARCROLE)
output_file = os.path.join(data_pool.output_folder, 'us-gaap-2021-presentations.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 3 \- View specific presentation hierarchy

Open US\-GAAP 2021 Financial Reporting Taxonomy and report presentation hierarchy with role http://fasb.org/us\-gaap/role/disclosure/BalanceSheetOffsetting in form of indented nodes, where each node is represented with concept label and QName. Click [here](/xbrl/us-gaap-2021-210.000.html) to view the result.

```
import os
from xbrl.base import pool, const
from xbrl.engines import tax_reporter

# US-GAAP taxonomy - version 2021
url = 'https://xbrl.fasb.org/us-gaap/2021/us-gaap-2021-01-31.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
package = data_pool.cache_package(url)
entry_point = 'https://xbrl.fasb.org/us-gaap/2021/entire/us-gaap-entryPoint-all-2021-01-31.xsd'
tax = data_pool.add_taxonomy([entry_point])
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
role = 'http://fasb.org/us-gaap/role/disclosure/BalanceSheetOffsetting'
# List presentation hierarchies in a HTML table
rep.r_base_set('presentationArc', role, const.PARENT_CHILD_ARCROLE)
output_file = os.path.join(data_pool.output_folder, 'us-gaap-2021-210.000.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 4 \- View extensible enumerations lists

View a specific domain\-member hierarchy in US\-GAAP 2021 taxonomy, which includes enumeration lists used for extensible enumerations concepts. Click [here](/xbrl/us-gaap-2021-enumeration_lists.html) to view result.

```
import os
from xbrl.base import pool, const
from xbrl.engines import tax_reporter

# US-GAAP taxonomy - version 2021
data_pool = pool.Pool()
tax = data_pool.add_package('https://xbrl.fasb.org/us-gaap/2021/us-gaap-2021-01-31.zip')
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# View specific domain-member base set, which contains enumeratino lists for extensible enumerations.
role = 'http://fasb.org/us-gaap/role/eedm/ExtensibleEnumerationLists'
rep.r_base_set('definitionArc', role, const.XDT_DOMAIN_MEMBER_ARCROLE)
output_file = os.path.join(data_pool.output_folder, 'us-gaap-2021-enumeration_lists.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 5 \- Extensible Enumeration Sets

US\-GAAP 2021 taxonomy has a number of concepts of type **enumerationSetItemType**. This report lists these concepts together with associated lists of enumeration members. Click [here](/xbrl/us-gaap-enumeration_sets.html) to view the result.

```
import os
from xbrl.base import pool
from xbrl.engines import tax_reporter

# US-GAAP taxonomy - version 2021
url = 'https://xbrl.fasb.org/us-gaap/2021/us-gaap-2021-01-31.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
tax = data_pool.add_package(url)
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# Render enumeration sets as HTML
rep.r_enumeration_sets()
output_file = os.path.join(data_pool.output_folder, 'us-gaap-enumeration_sets.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 6 \- Extensible Enumerations

EIOPA 2\.5\.0 taxonomy has reporting concepts of type **enumerationItemType**. The report lists these concepts together with associated lists of members. Click [here](/xbrl/eiopa-250-enumerations.html) to view the result.

```
import os
from xbrl.base import pool
from xbrl.engines import tax_reporter

# EIOPA Taxonomy version 2.5.0
url = 'https://dev.eiopa.europa.eu/Taxonomy/Full/2.5.0/S2/EIOPA_SolvencyII_XBRL_Taxonomy_2.5.0_hotfix.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
data_pool.cache_package(url)
entry_point = 'http://eiopa.europa.eu/eu/xbrl/s2md/fws/solvency/solvency2/2020-07-15/mod/qes.xsd'
tax = data_pool.add_taxonomy([entry_point])
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# Render enumeration sets as HTML
rep.r_enumerations()
output_file = os.path.join(data_pool.output_folder, 'eiopa-250-enumerations.html')
rep.save_as(output_file)
print(f'Report created in {output_file}')

```

## Example 7 \- Role Types and Arcrole Types

Loads NTP\-KVK version 15 (2020\) taxonomy and lists all **roleType** and **arcroleType** elements. Click [here](/xbrl/ntp15-kvk-roletypes.html) and [here](/xbrl/ntp15-kvk-arcroletypes.html) to view results.

```
import os
from xbrl.base import pool
from xbrl.engines import tax_reporter

# NTP-KVK Taxonomy for 2020
url = 'https://www.nltaxonomie.nl/nt15/kvk/20201209/entrypoints/kvk-rpt-jaarverantwoording-2020-ifrs-full.xsd'
data_pool = pool.Pool()
# Load the entrypoint directly from Web.
tax = data_pool.add_taxonomy([url])
# Create taxonomy reporter
rep = tax_reporter.TaxonomyReporter(tax)
# Create HTML report for role types
rep.r_role_types()
output_file = os.path.join(data_pool.output_folder, 'ntp15-kvk-roletypes.html')
rep.save_as(output_file)
# Create HTML report for arcrole types
rep.r_arcrole_types()
output_file = os.path.join(data_pool.output_folder, 'ntp15-kvk-arcroletypes.html')
rep.save_as(output_file)

```

## Example 8 \- Dimensional Relationship Sets

Loads EIOPA 2\.5\.0 \- qes and lists all dimensional relationship sets.

```
from xbrl.base import pool

# EIOPA Taxonomy version 2.5.0
url = 'https://dev.eiopa.europa.eu/Taxonomy/Full/2.5.0/S2/EIOPA_SolvencyII_XBRL_Taxonomy_2.5.0_hotfix.zip'
# Create the data pool and load taxonomy.
data_pool = pool.Pool()
data_pool.cache_package(url)
entry_point = 'http://eiopa.europa.eu/eu/xbrl/s2md/fws/solvency/solvency2/2020-07-15/mod/qes.xsd'
tax = data_pool.add_taxonomy([entry_point])
tax.compile_dr_sets()

for key, drs in tax.dr_sets.items():
    print()
    print(key)
    print('\nPrimary items')
    for pi in drs.primary_items.values():
        print(' '*10*pi.level, pi.concept.qname, pi.concept.get_label())
    print('\nHypercubes')
    for hc_key, hc in drs.hypercubes.items():
        print(hc.concept.qname, hc.concept.get_label())
        print('\nDimensions')
        for dim_key, dim in hc.dimensions.items():
            print(dim.concept.qname, dim.concept.get_label(), ' => ',
                  'typed ... ' if not dim.concept.is_explicit_dimension
                  else ','.join([m.qname for m in dim.members.values()] if dim.members else ''))

```

xbrl maintained by [fractalexperience](https://github.com/fractalexperience)

Published with [GitHub Pages](https://pages.github.com)
