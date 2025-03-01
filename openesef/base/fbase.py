import urllib.request, os
from lxml import etree as lxml
from openesef.base import ebase, util, const
from fs.base import FS
from typing import Optional
import fs
import re
from openesef.util.util_mylogger import setup_logger #util_mylogger
import logging 
if __name__=="__main__":
    logger = setup_logger("main", logging.INFO, log_dir="/tmp/log/")
else:
    logger = logging.getLogger("main.openesf.base.fbase") 


# import logging

# # Get a logger.  __name__ is a good default name.
# logger = logging.getLogger(__name__)
# #logger.setLevel(logging.DEBUG)

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

class XmlFileBase(ebase.XmlElementBase):
    def __init__(self, location=None, container_pool=None, parsers=None, root=None, esef_filing_root = None, memfs: Optional[FS] = None):
        """
        root = None
        this_xb = XmlFileBase(None, container_pool, parsers, root, esef_filing_root)
        """
        if parsers is None:
            parsers = {}
        self.parsers = parsers
        self.pool = container_pool
        self.memfs = memfs
        # Check if root_path is a mem:// URL
        self.location = location
        self.is_memory_fs = False 
        if esef_filing_root:
            self.is_memory_fs = esef_filing_root.startswith("mem://")
        elif memfs:
            self.is_memory_fs = True
        elif location and "mem://" in location:
            self.is_memory_fs = True
        elif self.pool and self.pool.memfs:
            self.is_memory_fs = True
        self.location = location
        if self.is_memory_fs and memfs is None:
            # Create memory filesystem if not provided
            raise ValueError("XmlFileBase: memfs is None and is_memory_fs is True")
        if not self.is_memory_fs:
            logger.info(f"XmlFileBase: is_mem_fs=False! location={location}, is_memory_fs={self.is_memory_fs}")
        self.namespaces = {}  # Key is the prefix and value is the URI
        self.namespaces_reverse = {}  # Key is the UrI and value is the prefix
        self.schema_location_parts = {}
        self.base = ''
        self.esef_filing_root = esef_filing_root        
        if location:
            self.location = util.reduce_url(location)
            # self.base = self.location.replace('\\', '/')[:location.rfind("/")]
            self.base = os.path.split(location)[0]
            if root is None:  # Only parsing file again the root element is not explicitly passed
                root = self.get_root()
        if root is None:
            return
        # Predefined
        self.namespaces['xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
        self.namespaces_reverse['http://www.w3.org/2001/XMLSchema-instance'] = 'xsi'
        self.l_namespaces(root)
        self.l_schema_location(root)
        #this_eb = ebase.XmlElementBase(e=None, parsers=None, assign_origin=False, esef_filing_root=None)
        #this_eb = ebase.XmlElementBase(e = root, parsers=parsers, assign_origin=False, esef_filing_root=esef_filing_root); #self = this_eb
        super().__init__(e = root, 
                         parsers = parsers, 
                         esef_filing_root=esef_filing_root)

    def get_root(self):
        """ If the location can be found in an open package, then extract it from the package """
        url = self.location
        # Handle packaged locations first
        if self.pool and self.pool.packaged_locations:
            t = self.pool.packaged_locations.get(url)
            if t:
                pck = t[0]
                content = pck.get_url(url)
                p = lxml.XMLParser(huge_tree=True)
                try:
                    return lxml.XML(content, parser=p)
                except Exception:
                    s = content.decode('utf-8')
                    s = s.replace('\n', '')  # Try to correct eventually broken lines
                    root = lxml.XML(bytes(s, encoding='utf-8'), parser=p)
                    return root

        # Handle memory filesystem
        if self.is_memory_fs and not "http" in url and not "file://" in url:
            if self.memfs is None:
                raise ValueError("XmlFileBase: self.is_memory_fs is True but  memfs is None")
            
            # Remove 'mem://' prefix to get the actual path
            mem_path = re.sub(r'^mem://', '', url)
            
            if self.memfs.exists(mem_path):
                with self.memfs.open(mem_path, 'rb') as f:
                    content = f.read()
                    p = lxml.XMLParser(huge_tree=True)
                    try:
                        return lxml.XML(content, parser=p)
                    except Exception:
                        s = content.decode('utf-8')
                        s = s.replace('\n', '')  # Try to correct eventually broken lines
                        root = lxml.XML(bytes(s, encoding='utf-8'), parser=p)
                        return root
            # else:
            #     raise FileNotFoundError(f"File {mem_path} not found in memory filesystem")

        # Handle regular filesystem and URLs
            logger.debug(f"XmlFileBase: get_root() did not find the file in memory filesystem; self.is_memory_fs = {self.is_memory_fs}; self.memfs.listdir('.') = {self.memfs.listdir('.')}")
        filename = url
        if self.pool:
            filename = self.pool.cache(url) # <- got the error
        elif url.startswith('http://') or url.startswith('https://'):
            filename, headers = urllib.request.urlretrieve(url)
        dom = lxml.parse(filename)
        return dom.getroot()

    def l_schema_location(self, e):
        sl = e.attrib.get(f'{{{const.NS_XSI}}}schemaLocation')
        if not sl:
            return
        parts = util.normalize(sl).split(' ')
        cnt = -1
        odds = []
        evens = []
        for p in parts:
            cnt += 1
            if cnt % 2:
                evens.append(p)
            else:
                odds.append(p)
        self.schema_location_parts = dict(zip(odds, evens))

    def l_namespaces(self, e):
        for prefix in filter(lambda x: x is not None, e.nsmap):
            uri = e.nsmap[prefix]
            self.namespaces[prefix] = uri
            self.namespaces_reverse[uri] = prefix

    def l_namespaces_rec(self, e, target_tags=None):
        if not isinstance(e, lxml._Element):
            return
        if target_tags is None or e.tag in target_tags:
            self.l_namespaces(e)
        for e2 in e.iterchildren():
            self.l_namespaces_rec(e2)
