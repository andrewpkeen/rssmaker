from urllib.request import Request, urlopen
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from enum import Enum
from hashlib import blake2s

base_url = 'https://www.dekudeals.com'
page = '/recent-drops?country=us'

hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
       'Accept-Language': 'en-US,en;q=0.8'}

class _State(Enum):
    IN_TITLE = 1
    IN_NAME = 2
    IN_DESCRIPTION = 3

class DekuDealsParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.rss = ET.Element('rss')
        self.rss.set('version', '2.0')
        # self.rss.set('xmlns:media', 'http://search.yahoo.com/mrss/')
        self.channel = ET.SubElement(self.rss, 'channel')

        link = ET.SubElement(self.channel, 'link')
        link.text = base_url + page

        self.item = None
        self.item_hash = None
        self.description = None
        self.state = None
        self.div_level = 0

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        class_attr = attr_dict.get('class')
        match tag:
            case 'title':
                self.state = _State.IN_TITLE
            case 'meta' if attr_dict.get('name') == 'description':
                description = ET.SubElement(self.channel, 'description')
                description.text = attr_dict.get('content')
            case 'div':
                if class_attr == 'position-relative':
                    self.item = ET.Element('item')
                    self.item_hash = blake2s()
                    self.description = ET.SubElement(self.item, 'description')
                    self.description.text = ''
                    self.div_level = 1
                elif class_attr == 'h6 name':
                    self.state = _State.IN_NAME
                    self.div_level = 2
                elif class_attr == 'w-100':
                    guid = ET.SubElement(self.item, 'guid')
                    guid.text = self.item_hash.hexdigest()
                    self.div_level = 2
                elif self.div_level > 0:
                    self.div_level += 1
            case 'a' if class_attr == 'main-link':
                link = ET.SubElement(self.item, 'link')
                link.text = base_url + attr_dict['href']
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
        if self.div_level > 1 and self.state != _State.IN_NAME:
            self.description.text += '</' + tag + '>'

        self.state = None

        if tag == 'div' and self.div_level > 0:
            self.div_level -= 1
            if self.div_level == 0:
                self.channel.append(self.item)
                self.item = None
                self.item_hash = None
                self.description = None

    def handle_data(self, data):
        match self.state:
            case _State.IN_TITLE:
                title = ET.SubElement(self.channel, 'title')
                title.text = data
            case _State.IN_NAME:
                title = ET.SubElement(self.item, 'title')
                title.text = data;
            case _ if self.div_level > 1:
                self.description.text += data
                self.item_hash.update(data.encode())


req = Request(base_url + page, headers=hdr)
with urlopen(req) as repsonse:
    parser = DekuDealsParser()
    while data := repsonse.read():
        parser.feed(data.decode())
    ET.ElementTree(parser.rss).write('dekudeals.xml')

