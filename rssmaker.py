from enum import Enum
from hashlib import md5
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_PAGES = 3

hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
       'Accept-Language': 'en-US,en;q=0.8'}

base_url = 'https://www.dekudeals.com'
page = '/recent-drops?country=us'
xml_file = 'dekudeals.xml'

class _State(Enum):
    IN_TITLE = 1
    IN_NAME = 2
    IN_DESCRIPTION = 3

def get_or_create_subelement(element, tag, index = None):
    if (subelement := element.find(tag)) is None:
        subelement = ET.Element(tag)
        if index is None:
            element.append(subelement)
        else:
            element.insert(index, subelement)
    return subelement

class DekuDealsParser(HTMLParser):

    def __init__(self, date):
        super().__init__()
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

        link = get_or_create_subelement(self.channel, 'link')
        link.text = base_url + page

        pubDate = get_or_create_subelement(self.channel, 'pubDate')
        pubDate.text = date
        lastBuildDate = get_or_create_subelement(self.channel, 'lastBuildDate')
        lastBuildDate.text = date

        self.pubDate = date

        if latest_item := self.channel.find('item'):
            self.latest_guid = latest_item.find('guid').text
        else:
            self.latest_guid = None

        self.index = 5
        self.item = None
        self.item_hash = None
        self.description = None
        self.state = None
        self.div_level = 0
        self.done = False
        self.changed = False

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
                    self.item_hash = md5()
                    self.description = ET.SubElement(self.item, 'description')
                    self.description.text = ''
                    ET.SubElement(self.item, 'pubDate').text = self.pubDate
                    self.div_level = 1
                elif class_attr == 'h6 name':
                    self.state = _State.IN_NAME
                    self.div_level = 2
                elif class_attr == 'w-100':
                    guid = ET.SubElement(self.item, 'guid')
                    guid.text = self.item_hash.hexdigest()
                    if guid.text == self.latest_guid:
                        self.done = True
                    self.div_level = 2
                elif self.div_level > 0:
                    self.div_level += 1
            case 'a' if class_attr == 'main-link':
                link = ET.Element('link')
                link.text = base_url + attr_dict['href']
                self.item.insert(0, link)
                self.item_hash.update(link.text.encode())
            case 'img' if class_attr and class_attr.startswith('responsive-img shadow-img'):
                enclosure = ET.SubElement(self.item, 'enclosure')
                url = attr_dict['src']
                enclosure.set('url', url)
                imgReq = Request(url, headers=hdr)
                with urlopen(imgReq) as response:
                    enclosure.set('length', response.getheader('Content-Length'))
                    enclosure.set('type', response.getheader('Content-Type'))
        if self.div_level > 1 and self.state != _State.IN_NAME:
            self.description.text += '<' + tag + '>'
                
    def handle_endtag(self, tag):
        if self.done:
            return
        
        if self.div_level > 1 and self.state != _State.IN_NAME:
            self.description.text += '</' + tag + '>'

        self.state = None

        if tag == 'div' and self.div_level > 0:
            self.div_level -= 1
            if self.div_level == 0:
                self.channel.insert(self.index, self.item)
                self.index += 1
                self.changed = True
                self.item = None
                self.item_hash = None
                self.description = None

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
            case _ if self.div_level > 1:
                self.description.text += data
                self.item_hash.update(data.encode())

parser = None
for i in range(1, MAX_PAGES + 1):
    req = Request(base_url + page + '?page=' + str(i), headers=hdr)
    with urlopen(req) as repsonse:
        if not parser:
            parser = DekuDealsParser(repsonse.getheader('Date'))
        while not parser.done and (data := repsonse.read()):
            parser.feed(data.decode())
    if parser.done:
        break
if parser.changed:
    print(str(parser.index - 5), "new items")
    parser.etree.write(xml_file)
else:
    print('Nothing new, no updates to file')

