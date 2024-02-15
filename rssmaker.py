from enum import Enum
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from re import compile, sub
from urllib.request import Request, urlopen
from urllib.error import URLError
from uuid import uuid4
import xml.etree.ElementTree as ET

MAX_ITEMS = 1067
MAX_PAGES = 36

ITEM_START_INDEX = 6

hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
       'Accept-Language': 'en-US,en;q=0.8'}

atom_uri = 'http://www.w3.org/2005/Atom'

setback_re = compile(r'\n(?P<value>\d+) (?P<units>[a-z]+)\nago\nat\n(?P<retailer>.+)\n')
time_format = '%a, %d %b %Y %H:%M:%S %Z'

base_url = 'https://www.dekudeals.com'
page = '/recent-drops?country=us'
xml_file = 'dekudeals.xml'
self_link = 'https://raw.githubusercontent.com/andrewpkeen/rssmaker/master/dekudeals.xml'

class _State(Enum):
    IN_TITLE = 1
    IN_NAME = 2
    IN_SETBACK = 3

def get_or_create_subelement(element, tag, index = None):
    if (subelement := element.find(tag)) is None:
        subelement = ET.Element(tag)
        if index is None:
            element.append(subelement)
        else:
            element.insert(index, subelement)
    return subelement

def make_datetime(datetimestr):
    return datetime.strptime(datetimestr, time_format).replace(tzinfo=timezone(timedelta(0), 'GMT'))

class DekuDealsParser(HTMLParser):

    def __init__(self, date):
        super().__init__()

        self.known_items = {}

        try:
            self.etree = ET.parse(xml_file)
            print('Using existing', xml_file, 'file')
            self.rss = self.etree.getroot()
        except FileNotFoundError:
            print('Creating new rss ElementTree')
            self.rss = ET.Element('rss')
            self.etree = ET.ElementTree(self.rss)
            self.rss.set('version', '2.0')

        self.channel = get_or_create_subelement(self.rss, 'channel')
        items = self.channel.findall('item')
        for i in range(len(items)):
            if i < MAX_ITEMS:
                self.known_items[items[i].findtext('link')] = items[i]
            else:
                self.channel.remove(items[i])
        print('Pre-existing items:', len(self.known_items))

        link = get_or_create_subelement(self.channel, 'link')
        link.text = base_url + page

        pubDate = get_or_create_subelement(self.channel, 'pubDate')
        lastBuildDate = get_or_create_subelement(self.channel, 'lastBuildDate')
        lastBuildDate.text = pubDate.text = date.strftime(time_format)

        self.pubDate = date

        atom_link = get_or_create_subelement(self.channel, f'{{{atom_uri}}}link', 3)
        atom_link.set('href', self_link)
        atom_link.set('rel', 'self')
        atom_link.set('type', 'application/rss+xml')

        self.index = ITEM_START_INDEX
        self.item = None
        self.description = None
        self.setback = None
        self.state = None
        self.div_level = 0
        self.done = False
        self.changed = False
        self.units = 'microseconds'

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        attr_dict = dict(attrs)
        class_attr = attr_dict.get('class')
        match tag:
            case 'title':
                self.state = _State.IN_TITLE
            case 'meta' if attr_dict.get('name') == 'description':
                description = get_or_create_subelement(self.channel, 'description', 1)
                description.text = attr_dict.get('content')
            case 'div':
                if class_attr == 'position-relative':
                    self.item = ET.Element('item')
                    self.description = ET.SubElement(self.item, 'description')
                    self.description.text = ''
                    self.setback = ''
                    self.div_level = 1
                elif class_attr == 'h6 name':
                    self.state = _State.IN_NAME
                    self.div_level = 2
                elif class_attr == 'w-100':
                    self.state = _State.IN_SETBACK
                    self.div_level = 2
                elif self.div_level > 0:
                    self.div_level += 1
            case 'a' if class_attr == 'main-link':
                link = ET.Element('link')
                link.text = base_url + attr_dict['href']
                self.item.insert(0, link)
            case 'img' if class_attr and class_attr.startswith('responsive-img shadow-img'):
                enclosure = ET.SubElement(self.item, 'enclosure')
                url = attr_dict['src']
                enclosure.set('url', url)
                imgReq = Request(url, headers=hdr)
                with urlopen(imgReq) as response:
                    enclosure.set('length', response.getheader('Content-Length'))
                    enclosure.set('type', response.getheader('Content-Type'))
            case _ if self.div_level > 1:
                self.description.text += f'<{tag}>'
                
    def handle_endtag(self, tag):
        if self.done:
            return
        
        match tag:
            case 'title':
                self.state = None
            case 'div':
                if self.div_level > 0:
                    if self.state == _State.IN_SETBACK:
                        setback_m = setback_re.match(self.setback)
                        pubDate = ET.SubElement(self.item, 'pubDate')
                        self.units = setback_m.group('units')
                        if self.units[-1] != 's':
                            self.units += 's'
                        td = timedelta(**{self.units: int(setback_m.group('value'))})
                        pubDate.text = (self.pubDate - td).strftime(time_format)
                        self.description.text += f' at {setback_m.group("retailer")} '
                    self.state = None
                    self.div_level -= 1
                    if self.div_level == 0:
                        self.description.text = sub('\s+', ' ', self.description.text).strip()
                        create_item = False
                        link = self.item.findtext('link')
                        known_item = self.known_items.get(link)
                        if known_item:
                            if self.description.text != known_item.findtext('description'):
                                self.channel.remove(known_item)
                                del self.known_items[link]
                                create_item = True
                            else:
                                ni_time = make_datetime(self.item.findtext('pubDate'))
                                ki_time = make_datetime(known_item.findtext('pubDate'))
                                if ni_time > ki_time + timedelta(**{self.units: 1}):
                                    self.channel.remove(known_item)
                                    del self.known_items[link]
                                    create_item = True
                                else:
                                    self.done = True
                        else:
                            create_item = True
                        if create_item:
                            guid = ET.SubElement(self.item, 'guid', {'isPermaLink': 'false'})
                            guid.text = str(uuid4())
                            self.channel.insert(self.index, self.item)
                            self.known_items[link] = self.item
                            self.index += 1
                            self.changed = True
                        self.item = None
                        self.description = None
                        self.setback = None
            case _ if self.div_level > 1:
                self.description.text += f'</{tag}>'

    def handle_data(self, data):
        if self.done:
            return
        
        match self.state:
            case _State.IN_TITLE:
                title = get_or_create_subelement(self.channel, 'title', 0)
                title.text = data
            case _State.IN_NAME:
                title = ET.Element('title')
                title.text = data;
                self.item.insert(0, title)
            case _State.IN_SETBACK:
                if self.div_level == 3:
                    self.setback += data
            case _ if self.div_level > 1:
                self.description.text += data

def execute():
    ET.register_namespace('atom', atom_uri)
    parser = None
    for i in range(1, MAX_PAGES + 1):
        page_url = base_url + page + f'&page={i}'
        req = Request(page_url, headers=hdr)
        try:
            with urlopen(req) as repsonse:
                if not parser:
                    date = make_datetime(repsonse.getheader('Date'))
                    print (f"Parsing update at {date:{time_format}}")
                    parser = DekuDealsParser(date)
                while not parser.done and (data := repsonse.read()):
                    parser.feed(data.decode())
        except URLError:
            print("Failed to open", page_url)
            if parser and parser.changed:
                print(str(parser.index - ITEM_START_INDEX), "new items")
                parser.etree.write(xml_file)
                print('Wrote to file. Quitting early.')
                exit(221)
            else:
                break
        if parser.done:
            break
    if parser and parser.changed:
        print(str(parser.index - ITEM_START_INDEX), "new items")
        parser.etree.write(xml_file)
    else:
        print('Nothing new, no updates to file')
    return parser and parser.changed

