"""
XBRL Pool Module Documentation

The Pool class serves as a central repository for managing XBRL taxonomies, instances, and related resources.
It inherits from Resolver class and provides functionality for loading, caching, and managing XBRL documents.

Key Features:
1. Taxonomy Management
   - Loading and caching taxonomies
   - Managing taxonomy packages
   - Handling multiple entry points

2. Instance Document Management
   - Loading instance documents from files, archives, or XML elements
   - Managing relationships between instances and taxonomies

3. Resource Management
   - Caching and resolving schemas and linkbases
   - Managing taxonomy packages
   - Handling alternative locations for resources

Class Attributes:
    taxonomies (dict): Stores loaded taxonomies
    current_taxonomy (Taxonomy): Reference to the currently active taxonomy
    current_taxonomy_hash (str): Hash identifier for the current taxonomy
    discovered (dict): Tracks discovered resources to prevent circular references
    schemas (dict): Stores loaded schema documents
    linkbases (dict): Stores loaded linkbase documents
    instances (dict): Stores loaded instance documents
    alt_locations (dict): Maps URLs to alternative locations
    packaged_entrypoints (dict): Maps entry points to package locations
    packaged_locations (dict): Maps locations to package contents
    active_packages (dict): Currently opened taxonomy packages
    active_file_archive (ZipFile): Currently opened archive file
"""
import sys



#import openesef
#print(openesef.__path__)
import os, zipfile, functools
from lxml import etree as lxml
from openesef.base import resolver, util
from openesef.taxonomy import taxonomy, schema, tpack, linkbase
#from openesef.taxonomy.linkbase import Linkbase
from openesef.instance import instance
import openesef
import gzip
from openesef.base import const, util
import os
#import tempfile
import zipfile
import functools
from pathlib import Path
import time
from typing import Optional, Dict, List, Union, Tuple
import traceback
import pathlib
from io import StringIO
import re 
import urllib.parse
from fs.base import FS
import fs
from openesef.util.util_mylogger import setup_logger #util_mylogger
import logging 
if __name__=="__main__":
    logger = setup_logger("main", logging.INFO, log_dir="/tmp/log/")
else:
    logger = logging.getLogger("main.openesf.base.pool") 


# import logging

# # Get a logger.  __name__ is a good default name.
# #logger = logging.getLogger(__name__)

# # Get the logger.  Don't create a new logger instance.
# logger = logging.getLogger("main.base.pool")
# #logger.setLevel(logging.DEBUG)
# logger.setLevel(logging.ERROR)

# # Check if handlers already exist and clear them to avoid duplicates.
# if logger.hasHandlers():
#     logger.handlers.clear()

# # Create a handler for console output.
# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)

# # Create a formatter.
# log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# formatter = logging.Formatter(log_format)

# # Set the formatter on the handler.
# handler.setFormatter(formatter)

# # Add the handler to the logger.
# logger.addHandler(handler)




class Pool(resolver.Resolver):
    def __init__(self, cache_folder=None, output_folder=None, alt_locations=None, esef_filing_root=None, max_error =0, memfs: Optional[FS] = None):
        """
        Initializes a new Pool instance
        Args:
            cache_folder (str): Path to cache directory
            output_folder (str): Path to output directory
            alt_locations (dict): Alternative URL mappings        
            esef_filing_root (str): Path to location of the ESEF structure
        """
        logger.info(f"\n\nInitializing Pool with cache_folder={cache_folder}, output_folder={output_folder}")
        if cache_folder is None:
            repo_cache_folder = Path(openesef.__file__).parent / "xbrl_schema"
            if os.path.exists(repo_cache_folder):
                if os.access(repo_cache_folder, os.W_OK):
                    cache_folder = repo_cache_folder
                    logger.info(f"Using repository cache folder: {cache_folder}")
            # if cache_folder is None:
            #     cache_folder = tempfile.gettempdir()
            #     logger.info(f"Using temporary cache folder: {cache_folder}")
        else:
            logger.info(f"Using provided cache folder: {cache_folder}")
        super().__init__(cache_folder, output_folder)
        self.taxonomies = {}
        self.current_taxonomy = None
        self.current_taxonomy_hash = None
        self.discovered = {}
        self.schemas = {}
        self.linkbases = {}
        self.instances = {}
        self.memfs = memfs
        if  memfs is None and esef_filing_root is not None and "mem://" in esef_filing_root: 
            raise ValueError("Pool: memfs is None and esef_filing_root is a memory URL")
        self.count_exceptions = 0
        # Alternative locations. If set, this is used to resolve Qeb references to alternative (existing) URLs. 
        self.alt_locations = alt_locations
        # Index of all packages in the cache/taxonomy_packages folder by entrypoint 
        self.packaged_entrypoints = {}
        self.packaged_locations = None
        # Currently opened taxonomy packages 
        self.active_packages = {}
        # Currently opened archive, where files can be read from - optional.
        self.active_file_archive = None
        self.esef_filing_root = esef_filing_root
        self.location = esef_filing_root
        self.co_domain = None
        self.max_error = max_error
    def __str__(self):
        return self.info()

    def check_count_exceptions(self):
        logger.debug(f"Checking count of exceptions: {self.count_exceptions}")
        logger.warning(f"Number of exceptions: {self.count_exceptions}")
        if self.count_exceptions > self.max_error:
            raise Exception(f"Number of exceptions exceeded {self.max_error}: {self.count_exceptions}")

    def __repr__(self):
        return self.info()

    def info(self):
        return '\n'.join([
            f'Taxonomies: {len(self.taxonomies)}',
            f'Instance documents: {len(self.instances)}',
            f'Taxonomy schemas: {len(self.schemas)}',
            f'Taxonomy linkbases: {len(self.linkbases)}',
            f"cache folder: {self.cache_folder}",
            ])

    def index_packages(self):
        """ Index the content of taxonomy packages found in cache/taxonomies/ """
        package_files = [os.path.join(r, file) for r, d, f in
                         os.walk(self.taxonomies_folder) for file in f if file.endswith('.zip')]
        for pf in package_files:
            self.index_package(tpack.TaxonomyPackage(pf))

    def index_package(self, package):
        """ Index the content of a taxonomy package """
        for ep in package.entrypoints:
            eps = ep.Urls
            for path in eps:
                self.packaged_entrypoints[path] = package.location

    def resolve_and_update_schema_refs(self, root, esef_filing_root):
        """
        Resolves and updates schemaRef elements within an ESEF context.
        Question: Why does it not change anything in `self` and no return values?
        """
        nsmap = {'link': const.NS_LINK}
        schema_refs = root.findall(".//link:schemaRef", namespaces=nsmap)
        logger.debug(f"  Calling resolve_and_update_schema_refs() with:\n    root {root} and esef_filing_root {esef_filing_root}")
        logger.debug(f"    found {len(schema_refs)} link(s) in schema_refs ")
        resolved_schemas = set()  # Keep track of resolved schemas

        for schema_ref in schema_refs:
            #schema_ref = schema_refs[0]; print(lxml.tostring(schema_ref))
            href = schema_ref.get(f'{{{const.NS_XLINK}}}href')
            if href:
                logger.debug(f"href found: {href}")
                resolved_href = self.resolve_esef_schema_ref(href, esef_filing_root)
                if resolved_href and resolved_href not in resolved_schemas:
                    schema_ref.set(f'{{{const.NS_XLINK}}}href', resolved_href)
                    resolved_schemas.add(resolved_href)  # Add to the set of resolved schemas
                    
                elif resolved_href in resolved_schemas:
                    logger.debug(f"    Skipping already resolved schema: {resolved_href}") # Skip if already resolved
                else:
                    logger.warning(f"    Could not resolve schema reference: {href}")
        logger.debug(f"")

    def resolve_esef_schema_ref(self, href, esef_filing_root):
        """Resolves schema references within an ESEF structure."""
        res_href = re.search(esef_filing_root + r"(.*)", href)
        if res_href:
            href_local = re.sub("file://", "", res_href.group(0))
            if os.path.isfile(href_local):
                resolved_href = pathlib.Path(href_local).as_uri()
                return resolved_href 
        else:
            resolved_path = os.path.abspath(os.path.join(esef_filing_root, href))
            if os.path.isfile(resolved_path):
                return pathlib.Path(resolved_path).as_uri()
            else:
                logger.warning(f"Schema file not found: {resolved_path}")
                return None
    def add_instance_stringio(self, contentio, key="instance", attach_taxonomy=True):
        """
        Adds an instance document from a StringIO object
        This function has yet to be implemented
        """
        xid = instance.Instance(location="stringIO", container_pool=self, esef_filing_root="")
        self.add_instance(xid, key, attach_taxonomy)
        return xid

    def add_instance_location(self, esef_filing_root, filename, key=None, attach_taxonomy=True):
        """
        Loads an instance document from a file location within an ESEF structure.
        """

        logger.debug(f"Starting to run with add_instance_location()! \n  esef_filing_root: {esef_filing_root}\n  filename: {filename}.")
        instance_location = os.path.join(esef_filing_root, filename)
        instance_location = os.path.abspath(instance_location)        
        logger.debug(f"  instance_location: {instance_location}")

        if key is None:
            key = instance_location
            logger.debug(f"  Setting key as instance_location (full local path).")

        # parser = lxml.XMLParser(huge_tree=True)
        # doc = lxml.parse(instance_location, parser=parser)
        # root = doc.getroot(); #lxml.tostring(root)[:100]
        # # Resolve schemaRefs relative to the *esef_filing_root*, not the instance file
        # self.resolve_and_update_schema_refs(root, esef_filing_root) # <= What does this do exactly???
        # # Write back the modified XML
        # doc.write(instance_location)

        xid = instance.Instance(location=instance_location, 
                container_pool=self, 
                esef_filing_root = esef_filing_root)
        #type(xid)

        try:            
            self.add_instance(xid, key, attach_taxonomy, esef_filing_root) # <= This causes the dead-lock endless loop.
            return xid

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            self.count_exceptions += 1
            self.check_count_exceptions()
            return None

    def add_instance_archive(self, archive_location, filename, key=None, attach_taxonomy=False):
        """
        Adds an XBRL instance from an archive file (supports both .zip and .gzip formats)
        
        Args:
            archive_location (str): Path to the archive file (.zip or .gzip)
            filename (str): Name of the file within the archive (for zip) or the original filename (for gzip)
            key (str, optional): Key to identify the instance. Defaults to None.
            attach_taxonomy (bool, optional): Whether to attach taxonomy. Defaults to False.
        
        Returns:
            Instance: The loaded XBRL instance or None if loading fails
        
        Raises:
            FileNotFoundError: If archive_location doesn't exist
            ValueError: If archive format is not supported
        """
        if not os.path.exists(archive_location):
            raise FileNotFoundError(f"Archive not found: {archive_location}")

        # Handle GZIP files
        if archive_location.endswith('.gzip'):
            try:
                with gzip.open(archive_location, 'rb') as gf:
                    content = gf.read()
                    root = lxml.XML(content)
                    return self.add_instance_element(
                        root,
                        filename if key is None else key,
                        attach_taxonomy
                    )
            except Exception as e:
                self.count_exceptions += 1
                self.check_count_exceptions()

                raise ValueError(f"Error processing gzip file: {str(e)}")

        # Handle ZIP files
        elif archive_location.endswith('.zip'):
            try:
                archive = zipfile.ZipFile(archive_location)
                zil = archive.infolist()
                xid_file = [f for f in zil if f.filename.endswith(filename)]
                
                if not xid_file:
                    raise ValueError(f"File {filename} not found in archive")
                    
                xid_file = xid_file[0]
                
                with archive.open(xid_file) as xf:
                    root = lxml.XML(xf.read())
                    return self.add_instance_element(
                        root,
                        xid_file if key is None else key,
                        attach_taxonomy
                    )
            except Exception as e:
                self.count_exceptions += 1
                self.check_count_exceptions()

                raise ValueError(f"Error processing zip file: {str(e)}")

        else:
            self.count_exceptions += 1
            self.check_count_exceptions()

            raise ValueError("Unsupported archive format. Use .zip or .gzip")
    
    def add_instance_element(self, e, key=None, attach_taxonomy=False):
        """
        Adds an instance document from an XML element
        Args:
            e (Element): XML element
            key (str): Optional identifier
            attach_taxonomy (bool): Whether to load associated taxonomy
        """
        xid = instance.Instance(container_pool=self, root=e, memfs=self.memfs)
        if key is None:
            key = e.tag
        self.add_instance(xid, key, attach_taxonomy)
        return xid

    def get_co_domain(self, esef_filing_root=None):
        if self.co_domain is None:
            for root, dirs, files in os.walk(esef_filing_root):
                #print(root, dirs, files)
                for dir in dirs:
                    if re.search(r"www.|.com|.de|.net", dir):
                        self.co_domain = dir
                        break
        return self.co_domain

    def get_co_xsd_local_path(self, ref, esef_filing_root):
        xsd_file_name = os.path.basename(ref)
        if self.co_domain:
            for root, dirs, files in os.walk(esef_filing_root):
                for file in files:
                    if re.search(xsd_file_name, file):
                        return os.path.join(root, file)  
        return ref
    def get_esef_local_path(self, ref, esef_filing_root):
        file_name = os.path.basename(ref)
        for root, dirs, files in os.walk(esef_filing_root):
                for file in files:
                    if re.search(file_name, file):
                        return os.path.join(root, file)  

    def add_instance(self, xid, key=None, attach_taxonomy=False, esef_filing_root=None, memfs=None): # Add esef_filing_root    
        """
        Adds an instance document to the pool
        Args:
            xid (Instance): The instance document to add
            key (str): Optional identifier
            attach_taxonomy (bool): Whether to load associated taxonomy
        """
        if key is None:
            #key = xid.location_ixbrl # < - AttributeError: 'Instance' object has no attribute 'location_ixbrl'
            key = xid.location

        self.instances[key] = xid # xid is of <class 'openesef.instance.instance.Instance'>
        if esef_filing_root and not self.co_domain:
            self.get_co_domain(esef_filing_root)
        if attach_taxonomy and xid.xbrl is not None:
            # Ensure that if schema references are relative, the location base for XBRL document is added to them
            if esef_filing_root is not None:
                entry_points = [  self.get_co_xsd_local_path(ref, esef_filing_root) if self.co_domain in ref  else ref for ref in xid.xbrl.schema_refs  ]
            entry_points = [ref if ref.startswith('http') or self.co_domain in ref else self.resolve_schema_ref(ref, xid.location)
                            for ref in entry_points]
            entry_points = [pathlib.Path(ep).as_uri() if os.path.isfile(ep) else ep for ep in entry_points]

            tax = self.add_taxonomy(entry_points, esef_filing_root, memfs) #<- here is the endless loop
            xid.taxonomy = tax

    def add_taxonomy(self, entry_points, esef_filing_root=None): # Add esef_filing_root
        """
        Adds a taxonomy from a list of entry points
        Args:
            entry_points (list): List of entry points
        Returns:
            Taxonomy: The loaded taxonomy object
        """
        logger.info("\n\Calling add_taxonomy(...):")
        ep_list = entry_points if isinstance(entry_points, list) else [entry_points]
        logger.info(f"Processing {len(ep_list)} entry points")

        # self.packaged_locations = {}
        for ep in ep_list:
            #ep = ep_list[0]
            #below is commented in original xbrl package.
            # if self.active_file_archive and ep in self.active_file_archive.namelist():
            #     self.packaged_locations[ep] = (self.active_file_archive, ep)
            # else:
            # For ESEF, try to resolve relative to esef_filing_root first
            if not ep.startswith(('http://', 'https://', 'file://')):
                potential_path = self.get_esef_local_path(ep, esef_filing_root)
                if potential_path and os.path.exists(potential_path):
                    ep = pathlib.Path(potential_path).as_uri()            
            
            self.add_packaged_entrypoints(ep) 

        key = ','.join(entry_points)
        logger.debug(f"Generated taxonomy key: {key}")

        if key in self.taxonomies:
            logger.debug(f"Taxonomy already loaded: {key}")
            return self.taxonomies[key]  # Previously loaded

        for ep in ep_list:
            logger.debug(f"ep: \n{ep}")

        #data_pool = Pool(cache_folder=CACHE_DIR, max_error=1); #self = data_pool
        #this_tax = taxonomy.Taxonomy(entry_points = [], container_pool = data_pool); self = this_tax
        #self = data_pool # when coming back
        this_tax = taxonomy.Taxonomy(entry_points=ep_list,
                          container_pool = self, 
                          esef_filing_root=esef_filing_root)  # <- endless loop
        # Sets the new taxonomy as current
        self.taxonomies[key] = self.current_taxonomy
        self.packaged_locations = None
        return self.current_taxonomy

    def add_packaged_entrypoints(self, ep): 
        """
        Adds packaged entry points
        Args:
            ep (str): Entry point
        Returns: None
        """
        pf = self.packaged_entrypoints.get(ep)
        if not pf:
            return  # Not found
        pck = self.active_packages.get(pf, None)
        if pck is None:
            pck = tpack.TaxonomyPackage(pf)
            pck.compile()
        self.index_package_files(pck)

    def index_package_files(self, pck):
        """
        Indexes files in a taxonomy package
        Args:
            pck (TaxonomyPackage): The taxonomy package object
        Returns: None
        """
        if self.packaged_locations is None:
            self.packaged_locations = {}
        for pf in pck.files.items():
            self.packaged_locations[pf[0]] = (pck, pf[1])  # A tuple

    def cache_package(self, location, esef_filing_root=None):
        """ 
        Stores a taxonomy package from a Web location to local taxonomy package repository 
        Args:
            location (str): Location of taxonomy package
        Returns:
            TaxonomyPackage: The loaded taxonomy package object
        """
        package = tpack.TaxonomyPackage(location, self.taxonomies_folder, esef_filing_root=esef_filing_root)
        self.index_packages()
        return package

    def _is_esef_package(self, package):
        """
        Checks if the given package is an ESEF taxonomy package
        Args:
            package: The taxonomy package to check
        Returns:
            bool: True if it's an ESEF package, False otherwise
        """
        # Check for typical ESEF package indicators
        if hasattr(package, 'meta_inf') and package.meta_inf:
            # Check for ESEF-specific metadata in taxonomyPackage.xml
            if hasattr(package.meta_inf, 'taxonomy_package'):
                meta = package.meta_inf.taxonomy_package
                # Check for ESEF identifiers in the metadata
                if any('esef' in str(identifier).lower() for identifier in meta.get('identifier', [])):
                    return True
        
        # Check for typical ESEF folder structure
        if hasattr(package, 'files'):
            file_paths = package.files.keys()
            has_reports = any('reports' in path.lower() for path in file_paths)
            has_taxonomy = any('taxonomy' in path.lower() for path in file_paths)
            if has_reports and has_taxonomy:
                return True
        
        return False    
    
    def add_package(self, location, esef_filing_root = None):
        """
        Adds a taxonomy package provided in the location parameter, creates a taxonomy 
        using all entrypoints in the package and returns the taxonomy object.
        Args:
            location (str): Location of taxonomy package
        Returns:
            Taxonomy: The loaded taxonomy object
        """
        package = self.cache_package(location, esef_filing_root)
        self.active_packages[location] = package
        entry_points = [f for ep in package.entrypoints for f in ep.Urls]
        # If we have a esef_filing_root and this is an ESEF package, resolve entry points
        if esef_filing_root and self._is_esef_package(package):
            resolved_entry_points = []
            for ep in entry_points:
                if not ep.startswith(('http://', 'https://', 'file://')):
                    # Try to find the entry point in the ESEF structure
                    for root, _, files in os.walk(esef_filing_root):
                        if os.path.basename(ep) in files:
                            resolved_path = os.path.join(root, os.path.basename(ep))
                            resolved_ep = pathlib.Path(resolved_path).as_uri()
                            resolved_entry_points.append(resolved_ep)
                            break
                    else:
                        # If not found, keep original
                        resolved_entry_points.append(ep)
                else:
                    resolved_entry_points.append(ep)
            entry_points = resolved_entry_points

        tax = self.add_taxonomy(entry_points, esef_filing_root=esef_filing_root)
        return tax

    def add_reference(self, href, base, esef_filing_root=None, memfs=None): # Add esef_filing_root
        """

        Loads referenced schema or linkbase
        Args:
            href (str): Reference URL
            base (str): Base URL for relative references
        Returns: None

        Calling add_reference(...): href:http://xbrl.fasb.org/srt/2018/elts/srt-2018-01-31.xsd from base:  and esef_filing_root: mem://
        """
        
        if href is None:
            return

        # Skip basic schema objects
        if any(domain in href for domain in ['http://xbrl.org', 'http://www.xbrl.org']):
            return
        elif re.search("xbrl.org", href):
            return
        # elif href.startswith("mem://"):
        #     logger.debug(f"Skipping reference: {href} because it is in memory")
        #     return

        if memfs is not None and self.memfs is None:
            self.memfs = memfs
        # Resolve the reference
        resolved_href = self._resolve_url(href, base, esef_filing_root)
        
        # Create a unique key that includes taxonomy context
        key = f'{self.current_taxonomy_hash}_{resolved_href}'
        
        # Check if already processed or processing
        if key in self.discovered:
            return
            
        # Mark as being processed
        self.discovered[key] = False

        if not esef_filing_root:
            logger.debug("No esef_filing_root provided, using self.esef_filing_root")
            esef_filing_root = self.esef_filing_root

        logger.debug(f"\n\nCalling add_reference(...): href:{href} from base: {base} and esef_filing_root: {esef_filing_root}")    

        # # Handle mem:// URLs
        # if esef_filing_root and esef_filing_root.startswith('mem://'):
        #     if not href.startswith(('http://', 'https://', 'mem://')):
        #         # Convert relative paths to mem:// paths
        #         if href.startswith('/'):
        #             href = f"mem://{href.lstrip('/')}"
        #         else:
        #             base_path = base[6:] if base.startswith('mem://') else base
        #             href = f"mem://{os.path.join(base_path, href)}"
        # elif esef_filing_root and not href.startswith('http'):
        #     res_href = re.search(esef_filing_root + r"(.*)", href)
        #     if res_href:
        #         href_local = re.sub("file://", "", res_href.group(0))
        #         if os.path.isfile(href_local):
        #             base = os.path.dirname(href_local)
        #             #resolved_href = pathlib.Path(href_local).as_uri()
        #             #return resolved_href 

        # Validate file extension
        allowed_extensions = ('xsd', 'xml', 'json')
        file_ext = href.split('.')[-1]
        if file_ext.lower() not in allowed_extensions:
            logger.warning(f"Skipping reference: Invalid file extension {file_ext}")
            return        


        # Handle alternative locations
        # Artificially replace the reference - only done for very specific purposes.
        if self.alt_locations and href in self.alt_locations:
            original_href = href
            href = self.alt_locations[href]
            logger.debug(f"Replaced href \n{original_href} \nwith alternative location \n{href}")            
            
        # Resolve URL # Generate unique key that includes the base path to prevent loops
        #resolved_href = href
        if not href.startswith(('http://', 'https://', "mem://")):
            if esef_filing_root:
                if esef_filing_root.startswith('mem://'):
                    # Handle memory filesystem paths
                    resolved_href = href  if not resolved_href else resolved_href
                else:                
                    # Try to resolve relative to esef_filing_root first                    
                    #href_filename = href.split("/")[-1] if len(href.split("/"))>0 else ""
                    res_href = re.search(esef_filing_root + r"(.*)", href)
                    if res_href:
                        href_local = re.sub("file://", "", res_href.group(0))
                        if os.path.isfile(href_local):
                            resolved_href = pathlib.Path(href_local).as_uri() 
                    else:
                        # Fall back to base path resolution
                        resolved_href = self._resolve_url(href, base, esef_filing_root)

                    # potential_path = self.get_esef_local_path(ep, esef_filing_root) # <- this is terribly wrong
                    # if os.path.exists(potential_path):
                    #     resolved_href = pathlib.Path(potential_path).as_uri()


            # Create a unique key that includes both href and base to prevent loops
            key = f'{self.current_taxonomy_hash}_{resolved_href}_{base}'
            
            if key in self.discovered:
                return
                
            self.discovered[key] = False

        try:
            if resolved_href.endswith(".xsd"):
                
                if resolved_href in self.schemas: # **CHECK IF ALREADY LOADED!**
                    logger.debug(f"Schema already loaded: {resolved_href}. Skipping.")
                    return  # Already loaded!                
                # sh = self.add_schema(resolved_href, esef_filing_root)
                # self.current_taxonomy.attach_schema(resolved_href, sh)                
                #logger.debug(f"Loading schema: \n{resolved_href}")
                if resolved_href.startswith("mem://"):
                    schema_path = resolved_href
                elif resolved_href.startswith("file://"):
                    schema_path = re.sub("file://", "", resolved_href) # Remove file:// for schema.Schema
                else:
                    schema_path = resolved_href # Use the URL directly
                logger.debug(f"schema_path: \n{schema_path}")
                #from openesef.taxonomy import taxonomy, schema, tpack, linkbase; from openesef.base import fbase, const, element, util
                #self=data_pool
                #self=data_pool; this_schema = schema.Schema(location="",container_pool=self); self = this_schema
                #self=data_pool; this_schema = schema.Schema(location=schema_path,container_pool=self); self = this_schema
                sh = self.schemas.get(
                    schema_path, 
                    schema.Schema(location=schema_path, 
                                  container_pool=self, 
                                  esef_filing_root=esef_filing_root, 
                                  memfs=self.memfs)) #<- Endless loop
                #if self.current_taxonomy:
                try:
                    self.current_taxonomy.attach_schema(schema_path, sh)
                except Exception as e:
                    logger.error(f"Failed to attach schema: location={schema_path}, esef_filing_root={esef_filing_root} \n{str(e)}")
                    traceback.print_exc(limit=10)
            else:
                if resolved_href in self.linkbases: # **CHECK IF ALREADY LOADED!**
                    logger.debug(f"Linkbase already loaded: {resolved_href}. Skipping.")
                    return # Already loaded!
                                
                logger.debug(f"Loading linkbase by pool.add_reference(...): {resolved_href}")
                # Remove file:// prefix if present
                if resolved_href.startswith("mem://"):
                    linkbase_path = re.sub("mem://", "", resolved_href)
                elif resolved_href.startswith("file://"):
                    linkbase_path = re.sub("file://", "", resolved_href)
                else:
                    linkbase_path = resolved_href
                #from openesef.taxonomy import linkbase
                #this_lb = linkbase.Linkbase(location=None, container_pool=self, esef_filing_root=esef_filing_root) #self = this_lb
                try:
                    this_lb = linkbase.Linkbase(location=linkbase_path, container_pool=self, esef_filing_root=esef_filing_root, memfs=self.memfs) #<- got error
                    lb = self.linkbases.get(resolved_href, this_lb) # <- got the error
                    #if self.current_taxonomy:
                    self.current_taxonomy.attach_linkbase(resolved_href, lb) # Use resolved_href
                except Exception as e:
                    logger.error(f"Failed to load linkbase: locatioon={resolved_href}, esef_filing_root={esef_filing_root} \n{str(e)}")
                    traceback.print_exc(limit=10)
                #data_pool = Pool(cache_folder=CACHE_DIR, max_error=1); #self = data_pool
                #this_lb = linkbase.Linkbase(location=None, container_pool=data_pool, esef_filing_root=esef_filing_root) #self = this_lb

        except OSError as e:
            self.count_exceptions += 1
            self.check_count_exceptions()

            logger.error(f"OSError Failed to load resource \n{href} \n{str(e)}")
            # Log the error but don't raise it to allow continued processing
            traceback.print_exc(limit=10)

        except Exception as e:
            self.count_exceptions += 1
            self.check_count_exceptions()

            logger.error(f"Failed to load resource \n{href} \n{str(e)}")
            traceback.print_exc(limit=10)

    @staticmethod
    def check_create_path(existing_path, part):
        new_path = os.path.join(existing_path, part)
        if not os.path.exists(new_path):
            os.mkdir(new_path)
        return new_path

    def save_output(self, content, filename):
        """
        Saves content to output directory
        Args:
            content (str): Content to save
            filename (str): Target filename
        Returns: None        
        """
        if os.path.sep in filename:
            functools.reduce(self.check_create_path, filename.split(os.path.sep)[:-1], self.output_folder)
        location = os.path.join(self.output_folder, filename)
        with open(location, 'wt', encoding="utf-8") as f:
            f.write(content)


    def _resolve_url(self, href: str, base: Optional[str], esef_filing_root: Optional[str] = None) -> str:
        """
        Resolves URLs, correctly handling relative paths and file URLs.
        Returns a file URL for local files and an absolute URL for remote resources.
        
        Calling _resolve_url(...): href: srt-types-2020-01-31.xsd, base: http://xbrl.fasb.org/srt/2020/elts, esef_filing_root: mem://
        Resolved URL (mem base):  http://xbrl.fasb.org/srt/2020/srt-types-2020-01-31.xsd

        """
        logger.debug(f"==  Calling _resolve_url(...): href: {href}, base: {base}, esef_filing_root: {esef_filing_root}")

        if href.startswith(('http://', 'https://', 'mem://', 'file://')):
            logger.debug(f"Resolved HTTP URL: \n{href}")
            return href
        elif base.startswith(('http://', 'https://', 'mem://', 'file://')):
            #print(f"20250215a:{base}{href}")
            #return f"{base}/{href}"
            if not base.endswith("/"):
                base += "/"
            resolved_path = urllib.parse.urljoin(base, href)
            logger.debug(f"Resolved URL (mem base): \n{resolved_path}")
            return resolved_path            
        # Try to find the file in ESEF structure first
        if esef_filing_root :
            if not "mem://" in esef_filing_root:
                # First, try to find in www.company.com subdirectory
                for root, _, files in os.walk(esef_filing_root):
                    if os.path.basename(href) in files:
                        resolved_path = os.path.join(root, os.path.basename(href))                    
                        resolved = pathlib.Path(resolved_path).as_uri()
                        #logger.debug(f"Resolved URL (esef_filing_root): \n{resolved}")
                        return resolved

                esef_filing_root_parent = os.path.dirname(esef_filing_root)
                _i_walk = 0 
                for root, _, files in os.walk(esef_filing_root_parent):
                    _i_walk += 1
                    if _i_walk > 16:
                        break
                    if os.path.basename(href) in files:
                        resolved_path = os.path.join(root, os.path.basename(href))
                        
                        resolved = pathlib.Path(resolved_path).as_uri()
                        #logger.debug(f"Resolved URL (esef_filing_root): \n{resolved}")
                        return resolved
            else:
                logger.debug(f"Resolved URL (mem esef_filing_root): \n{esef_filing_root}")
                for root, _, files in self.memfs.walk("."):
                    if os.path.basename(href) in files:
                        resolved_path = os.path.join("mem://", root, os.path.basename(href))
                        resolved = pathlib.Path(resolved_path).as_uri()
                        #logger.debug(f"Resolved URL (esef_filing_root): \n{resolved}")
                        return resolved
            # If not found in www subdirectory, try base directory
        if base:
            if base.startswith(('http://', 'https://', 'mem://', 'file://')):
                resolved_path = f"{base}/{href}"
            else:
                resolved_path = os.path.abspath(os.path.join(os.path.dirname(base), href)) #<- this is wrong? #20250215
            #print(f"href: \n{href} -> resolved_path: \n{resolved_path}")
            #print(f"base: \n{base}")
            if os.path.isfile(resolved_path):
                resolved = pathlib.Path(resolved_path).as_uri()
                #logger.debug(f"Resolved URL (ESEF base): \n{resolved}")
                return resolved

        if base is None or not base.strip():
            if os.path.isfile(href):
                resolve_result = pathlib.Path(os.path.abspath(href)).as_uri()
                #logger.debug(f"Resolved URL: \n{href} to \n{resolve_result}")
                return resolve_result # Ensure absolute path
            else:  
                #logger.debug(f"Resolved URL: \n{href}")
                ##return f"https://{href}" # Assume it's a remote URL and prepend https://
                return href # Don't assume https, could be a relative local path
        if base.startswith(('http://', 'https://', 'mem://', 'file://')):
            resolved = urllib.parse.urljoin(base, href)
        elif base.startswith('file://') or base.startswith("/"):
            try:  # Use try-except to handle potential parsing errors
                base_path = urllib.parse.urlparse(base).path
                resolved_path = os.path.abspath(os.path.join(os.path.dirname(base_path), href))
                resolved = pathlib.Path(resolved_path).as_uri()
            except ValueError: # Log the error and return the original href
                self.count_exceptions += 1
                self.check_count_exceptions()
                logger.error(f"Invalid base URL: {base}")
                return href # Or handle the error differently, e.g., raise an exception
        else:  # base is a local path
            resolved_path = os.path.abspath(os.path.join(os.path.dirname(base), href))
            resolved = pathlib.Path(resolved_path).as_uri()

        logger.debug(f"Resolved URL: \n{resolved}")
        return resolved

    def resolve_schema_ref(self, href, instance_path):
        """
        Resolves schema reference URL.  Returns a local file path or an absolute URL.
        """
        logger.debug(f"Resolving schema reference: \n{href}")

        if href.startswith(('http://', 'https://', 'file://')):
            return href  # Already an absolute URL

        # Resolve relative to the instance_path
        #resolved_path= os.path.abspath(os.path.join(os.path.dirname(instance_path), href))
        #resolved_path = os.path.abspath(os.path.join(os.path.dirname(instance_path), href)) # Ensure absolute path
        #logger.debug(f"Resolved path: \n{resolved_path}")
        # Construct the full URL if href is relative
        base_url = os.path.dirname(instance_path)  # Get the base URL from the instance path
        resolved_path = os.path.abspath(os.path.join(base_url, href))  # Resolve relative path
        logger.debug(f"Resolved path: \n{resolved_path}")

        return resolved_path # Return the absolute path; don't prepend https://

    def add_schema(self, location, esef_filing_root=None, memfs=None):
        """
        Adds a schema to the pool and returns the Schema object
        
        Args:
            location (str): Location/URL of the schema
            esef_filing_root (str, optional): Root directory of ESEF filing
            
        Returns:
            Schema: The loaded schema object or None if already loaded
        """
        logger.debug(f"Adding schema by add_schema() from location: {location}")
        
        # If schema is already loaded, return existing instance
        if location in self.schemas:
            logger.debug(f"Schema already loaded: {location}")
            return self.schemas[location]
            
        try:
            # Create new schema instance
            schema_obj = schema.Schema(
                location=location,
                container_pool=self,
                esef_filing_root=esef_filing_root,
                memfs=memfs
            )
            
            # Store in schemas dictionary
            self.schemas[location] = schema_obj
            
            logger.debug(f"Successfully loaded schema: {location}")
            return schema_obj
            
        except Exception as e:
            logger.error(f"Failed to load schema {location}: {str(e)}")
            logger.error(f"traceback: \n{traceback.format_exc()}")
            self.count_exceptions += 1
            self.check_count_exceptions()
            return None

    def add_reference_from_string(self, content, location, base=''):
        """
        Loads referenced schema or linkbase from a string content
        
        Args:
            content (str): The XML content as a string
            location (str): Virtual location/URL for the content
            base (str): Base URL for relative references
        Returns: None
        """
        if location is None:
            return

        # Skip basic schema objects
        if any(domain in location for domain in ['http://xbrl.org', 'http://www.xbrl.org']):
            return
        elif re.search("xbrl.org", location):
            return

        # Create a unique key that includes taxonomy context
        key = f'{self.current_taxonomy_hash}_{location}'
        
        # Check if already processed or processing
        if key in self.discovered:
            return
            
        # Mark as being processed
        self.discovered[key] = True

        try:
            # Cache the content first
            cached_path = self.cache_from_string(StringIO(content), location)
            if location.endswith(".xsd"):
                logger.debug(f"Loading schema from string: {location}")
                
                sh = self.schemas.get(
                    location,
                    schema.Schema(
                        location=cached_path,
                        container_pool=self,
                        esef_filing_root=self.esef_filing_root
                    )
                )
                self.current_taxonomy.attach_schema(location, sh)
            else:
                logger.debug(f"Loading linkbase from string: {location}")
                
                lb = self.linkbases.get(
                    location,
                    linkbase.Linkbase(
                        location=cached_path,
                        container_pool=self,
                        esef_filing_root=self.esef_filing_root
                    )
                )
                self.current_taxonomy.attach_linkbase(location, lb)

        except Exception as e:
            self.count_exceptions += 1
            self.check_count_exceptions()
            logger.error(f"Failed to load resource from string {location}: {str(e)}")
            traceback.print_exc(limit=10)    

    def add_schema_from_string(self, content, location, esef_filing_root=None, memfs=None):
        """
        Adds a schema to the pool from a string content and returns the Schema object
        
        Args:
            content (str): The schema XML content as a string
            location (str): Virtual location/URL for the schema
            esef_filing_root (str, optional): Root directory of ESEF filing
        Returns:
            Schema: The loaded schema object or None if already loaded
        """
        logger.debug(f"Adding schema from string content with virtual location: {location}")
        
        # If schema is already loaded, return existing instance
        if location in self.schemas:
            logger.debug(f"Schema already loaded: {location}")
            return self.schemas[location]
            
        try:
            # First cache the content
            cached_path = self.cache_from_string(StringIO(content), location)
            
            # Create new schema instance using the cached file
            schema_obj = schema.Schema(
                location=cached_path,  # Use cached file path for actual content
                container_pool=self,
                esef_filing_root=esef_filing_root,
                memfs=memfs,
                virtual_location=location  # Pass original location for reference tracking
            )
            
            # Store in schemas dictionary using the virtual location
            self.schemas[location] = schema_obj
            
            logger.debug(f"Successfully loaded schema from string: {location}")
            return schema_obj
            
        except Exception as e:
            logger.error(f"Failed to load schema from string {location}: {str(e)}")
            self.count_exceptions += 1
            self.check_count_exceptions()
            return None

# to test Apple
if __name__ == "__main__" and False:
    #from openesef.base.pool import *
    CACHE_DIR = os.path.expanduser("~/.xbrl_cache")
    os.makedirs(CACHE_DIR, exist_ok=True)
    # Initialize pool with cache
    data_pool = Pool(cache_folder=CACHE_DIR, max_error=1); #self = data_pool
    this_tax = data_pool.add_taxonomy(entry_points=["http://xbrl.fasb.org/srt/2020/elts/srt-eedm1-def-2020-01-31.xml"], esef_filing_root=os.getcwd())

if __name__ == "__main__":
    import requests
    # Apple's 10-K iXBRL and XBRL URLs
    # https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/0000320193-20-000096-index.htm
    #location_ixbrl = 'https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/000032019320000096/aapl-20200926.htm'
    location_xbrl = 'https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926_htm.xml'
    location_taxonomy = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926.xsd"
    location_linkbase_cal = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926_cal.xml"
    location_linkbase_def = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926_def.xml"
    location_linkbase_lab = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926_lab.xml"
    location_linkbase_pre = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926_pre.xml"


    # Process both inline XBRL and native XBRL formats
    # Parse inline document (iXBRL)
    CACHE_DIR = os.path.expanduser("~/.xbrl_cache")
    data_pool = Pool(cache_folder=CACHE_DIR, max_error=10); #self = data_pool
    files = []
    for location in [location_xbrl, location_taxonomy, location_linkbase_cal, location_linkbase_def, location_linkbase_lab, location_linkbase_pre]:
        files.append(location.split('/')[-1])
        if not os.path.exists(location.split('/')[-1]):
            response = requests.get(location, headers={'User-Agent': 'Your Name <your.email@example.com>'})
            # Save the response content to a file
            with open(location.split('/')[-1], 'wb') as file:
                file.write(response.content)

    this_tax = data_pool.add_taxonomy(files, esef_filing_root=os.getcwd())
    #location = "https://xbrl.fasb.org/us-gaap/2024/elts/us-gaap-all-2024.xsd"
    #taxonomy = data_pool.add_taxonomy(files, esef_filing_root=os.getcwd())
    print("\nTaxonomy statistics:")
    print(f"Schemas: {len(this_tax.schemas)}")
    print(f"Linkbases: {len(this_tax.linkbases)}")
    print(f"Concepts: {len(this_tax.concepts)}")

# to test ESEF
if __name__ == "__main__" and False:
    """
    We run in first openesef folder. 
    Starting to parse for observation: gvkey=352123; 
    full_instance_path=/Users/mbp16/Dropbox/data/proj/bmcg/bundesanzeiger/public/352123/2023/marley_spoon_2024-05-10_esef_xmls/222100A4X237BRODWF67-2023-12-31-en/marleyspoongroup/reports/222100A4X237BRODWF67-2023-12-31-en.xhtml
2025-02-12 20:20:01,955 - main.parse_concepts - PID:13347 - INFO - concept_to_df: 
    """
    #import importlib; import openesef.base.pool; from openesef.base.pool import *
    #import importlib; import openesef.openesef.base.pool; importlib.reload(openesef.openesef.base.pool); from openesef.openesef.base.pool import *
    #from openesef.base.pool import *
    #esef_filing_root="/Users/mbp16/Dropbox/data/proj/bmcg/bundesanzeiger/public/103487/2022/sap_Jahres-_2023-04-05_esef_xmls/sap-2022-12-31-DE/"
    #filename="reports/sap-2022-12-31-DE.xhtml"
    esef_filing_root = "/Users/mbp16/Dropbox/data/proj/bmcg/bundesanzeiger/public/352123/2023/marley_spoon_2024-05-10_esef_xmls/222100A4X237BRODWF67-2023-12-31-en/marleyspoongroup/"
    filename = "reports/222100A4X237BRODWF67-2023-12-31-en.xhtml"    
    data_pool = Pool(cache_folder="../../data/xbrl_cache", esef_filing_root=esef_filing_root); 
    #data_pool = Pool(cache_folder="../data/xbrl_cache", esef_filing_root=esef_filing_root, max_error=1024); 
    #self = data_pool; attach_taxonomy=True
    data_pool.add_instance_location(esef_filing_root=esef_filing_root, filename=filename, attach_taxonomy=True)
    #esef_filing_root = taxonomy_folder
    entry_point = None
    presentation_file = None
    for root, dirs, files in os.walk(esef_filing_root):
        for file in files:
            if file.endswith('.xsd'):
                entry_point = os.path.join(root, file)
            elif file.endswith('_pre.xml'):
                presentation_file = os.path.join(root, file)    
    tax = data_pool.add_taxonomy(entry_points = [entry_point, presentation_file], esef_filing_root=esef_filing_root)

