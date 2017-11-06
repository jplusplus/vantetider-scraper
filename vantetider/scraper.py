# encoding: utf-8
import requests
from bs4 import BeautifulSoup
import requests_cache
from itertools import product
import re
from requests.exceptions import HTTPError

requests_cache.install_cache()

from statscraper import (BaseScraper, Collection, DimensionValue,
                         Dataset, Dimension, Result)

BASE_URL = u"http://www.vantetider.se/Kontaktkort/"
NOT_IMPLEMENTED_DATASETS = [
    # Uses query params to populate search:
    "Aterbesok", "Undersokningar",

    # Table parsing fails on:
    "BUPdetalj", "BUP",
    ]

class VantetiderScraper(BaseScraper):

    def _fetch_itemslist(self, current_item):
        # Get start page
        html = self._get_html(BASE_URL + "Sveriges")
        soup = BeautifulSoup(html, 'html.parser')
        # Get links to datasets
        links = soup.find_all("ul", {"class":"main-nav page-width"})[0]\
            .find_all("li")[1]\
            .find_all("a")\
            [2:] # First two are _not relevant

        ids = [x.get("href").split("/Sveriges/")[-1].replace("/","")
               for x in links]
        labels = [x.text for x in links]

        for id_, label in zip(ids, labels):
            # Get html of dataset page
            if id_ not in NOT_IMPLEMENTED_DATASETS:
                yield VantetiderDataset(id_, label=label)

    def _fetch_dimensions(self, dataset):
        try:
            form = [x for x in dataset.soup.find_all("form")
                if "/Kontaktkort/" in x.get("action")][0]
        except IndexError:
            # http://www.vantetider.se/Kontaktkort/Sveriges/Aterbesok
            # does not have form element
            form = dataset.soup.find("div", {"class": "container_12 filter_section specialised_operation"})
        self._form = form

        # 1. Get select elements (dropdowns)
        select_elems = form.find_all("select")
        for elem in select_elems:
            elem_id = elem.get("name")
            dim_id = elem_id.replace("select_", "").replace("revisits_", "")
            dim = VantetiderDimension(dim_id)
            dim.elem_id = elem_id
            dim.elem = elem
            yield dim

        # 2. Get checkboxes (gender, ownership)
        checkbox_elems = [x for x in form.find_all("input", {"type": "checkbox"})]
        checkbox_labels = [x.text for x in form.find_all("label", {"class": "checkbox"})]
        for elem, label in zip(checkbox_elems, checkbox_labels):
            elem_id = elem.get("name")
            dim_id = elem_id.replace("checkbox_","")

            dim = VantetiderDimension(dim_id)
            dim.elem_id = elem_id
            dim.elem = elem
            yield dim


        # 3. Get radio buttons
        radio_elems = [x for x in form.find_all("input", {"type": "radio"})]
        elem_ids = get_unique([x.get("name") for x in radio_elems])

        for elem_id in elem_ids:
            elems = [x for x in radio_elems if x.get("name") == elem_id]
            dim_id = elem_id.replace("","")

            dim = VantetiderDimension(dim_id)
            dim.elem_id = elem_id
            dim.elem = elems
            yield dim


        # 4. Add measure and measure key
        yield VantetiderDimension("measure", label="Nyckeltal")

        # 5. Add unit id as own dimension
        yield VantetiderDimension("unit_id")

    def _fetch_allowed_values(self, dimension):
        """Allowed values are only implemented for regions.
        Ie units would need to be fetched trough an json api.
        """
        if dimension.id == "region":
            for option in dimension.elem.find_all("option"):
                _id = option.attrs["value"]
                label = option.text
                yield DimensionValue(_id, dimension, label=label)

        elif dimension.id == "year":
            for option in dimension.elem.find_all("option"):
                year = option.text
                yield DimensionValue(year, dimension)
        elif dimension.elem_type == "radio":
            input_tags = parse_radio_inputs(dimension.elem)
            for (_id, label, checked) in input_tags:
                yield DimensionValue(_id, dimension, label=label)

        else:
            pass


    def _fetch_data(self, dataset, query):
        if query is None:
            query = {}
        only_region = query.keys() == ["region"]
        NO_QUERY_DIMS = ["measure", "unit_id"]
        #
        NOT_IMPLEMENTED_DIMS = ["unit", "services"]

        for dim_id in NOT_IMPLEMENTED_DIMS:
            if dim_id in query.keys():
                msg = "Querying by {} is not implemented.".format(dim_id)
                raise NotImplementedError(msg)

        form_keys = [x.elem_id for x in dataset.dimensions if x.id not in NO_QUERY_DIMS]

        queries = []

        # Create payload for post request
        # Get a list of values to query by
        query_values = []
        for dim in dataset.dimensions:
            if dim.id in NO_QUERY_DIMS:
                continue

            # Pass default value if dimension is not in query
            if dim.id not in query:
                values = [dim.default_value]

            else:
                # Translate passed values to ids
                values = query[dim.id]
                if not isinstance(values, list):
                    values = [values]

            query_values.append(values)

        queries = list(product(*query_values))

        n_queries = len(queries)
        self.log.info(u"Making a total of {} queries".format(n_queries))

        for i, _query in enumerate(queries):
            self.log.info("Query {}/{}".format(i+1, n_queries))
            payload = dict(zip(form_keys, _query))
            url = dataset.get_url(payload["select_region"])

            for row in dataset._parse_result_page(url, payload,
                                                  only_region=only_region,
                                                  region=payload["select_region"]):
                yield row


    # HELPER METHODS
    def _get_html(self, url):
        """ Get html from url
        """
        self.log.info(u"/GET {}".format(url))
        r = requests.get(url)
        if hasattr(r, 'from_cache'):
            if r.from_cache:
                self.log.info("(from cache)")

        r.raise_for_status()

        return r.content

    def _post_html(self, url, payload):
        self.log.info(u"/POST {} with {}".format(url, payload))
        r = requests.post(url, payload)
        r.raise_for_status()

        return r.content

    def _get_json(self, url):
        """ Get json from url
        """
        self.log.info(u"/GET " + url)
        r = requests.get(url)
        if hasattr(r, 'from_cache'):
            if r.from_cache:
                self.log.info("(from cache)")
        r.raise_for_status()

        return r.json()



    @property
    def log(self):
        if not hasattr(self, "_logger"):
            self._logger = PrintLogger()
        return self._logger


class VantetiderDataset(Dataset):

    def get_url(self, region="Sverige"):
        if region=="Sverige":
            # Hack: _get_region_slug expects the page to be loaded, but to be
            # able to load the page we first have to show it on national levle
            region_slug = "Sveriges"
        else:
            region_slug = self._get_region_slug(region)
        return BASE_URL + region_slug + "/" + self.id

    @property
    def html(self):
        if not hasattr(self, "_html"):
            url = self.get_url()
            self._html = self.scraper._get_html(url)
        return self._html

    @property
    def soup(self):
        return BeautifulSoup(self.html, 'html.parser')

    @property
    def regions(self):
        """ Get a list of all regions
        """
        return self.dimensions["region"].allowed_values

    @property
    def years(self):
        """ Get a list of all available years
        """
        return self.dimensions["year"].allowed_values

    @property
    def latest_timepoint(self):
        """Get the latest available year and period.

        This method will have to be re-written to support pages with ajax load
        """
        return {
            "year": self.dimensions["year"].default_value,
            "period": self.dimensions["period"].default_value,
        }


    def _get_region_slug(self, id_or_label):
        """ Get the regional slug to be used in url
            "Norrbotten" => "Norrbottens"

            :param id_or_label: Id or label of region
        """
        region = self.regions.get_by_label(id_or_label)
        if region is None:
            try:
                region = self.regions[id_or_label]
            except StopIteration:
                # this is a strange error thrown by statscraper
                raise KeyError(u"{} is not a valid region id or label".format(id_or_label))

        slug = region.label\
            .replace(u" ","-")\
            .replace(u"ö","o")\
            .replace(u"Ö","O")\
            .replace(u"ä","a")\
            .replace(u"å","a")

        if not "region" in slug:
            slug = slug + "s"

        EXCEPTIONS = {
            "Jamtland-Harjedalens": "Jamtlands",
            "Rikets": "Sveriges",
            "Alla-landstings": "Sveriges",
        }
        if slug in EXCEPTIONS:
            slug = EXCEPTIONS[slug]

        return slug

    def _parse_result_page(self, url, payload, only_region=False, region=None):
        """ Get data from a result page
            :param url: url to query
            :param payload: payload to pass
            :return: a dictlist with data
        """
        data = []
        if only_region:
            html = self.scraper._get_html(url)
        else:
            try:
                html = self.scraper._post_html(url, payload=payload)
            except HTTPError, e:
                if e.response.status_code == 500:
                    self.scraper.log.warning(u"Unable to get {} with {}".format(url, payload))
                    return []

        current_selection = self._get_current_selection(html)

        table = Datatable(html)
        data = []
        _region = None
        for row in table.data:
            region_or_unit_id, region_or_unit_label = row["region_or_unit"]
            region = self.regions.get_by_label(region_or_unit_label)
            if region:
                row["region"] = region.label
                row["unit"] = None
                row["unit_id"] = None
                _region = region.label
            else:
                assert region_or_unit_label is not None
                assert region_or_unit_id is not None

                row["region"] = _region
                row["unit"] = region_or_unit_label
                row["unit_id"] = region_or_unit_id

            value = row["value"]

            row.pop("value", None)
            row.pop("region_or_unit", None)

            for dim in self.dimensions:
                if dim.id not in row:
                    row[dim.id] = current_selection[dim.id][1] # gets label
            data.append(Result(value, row))

        return data

    def _get_current_selection(self, html):
        if isinstance(html, str):
            html = BeautifulSoup(html, "html.parser")
        current_selection = {}
        for dim in self.dimensions:
            if dim.id in ["measure", "unit_id"]:
                continue

            elem = html.select("[name={}]".format(dim.elem_id))

            if len(elem) == 0:
                raise Exception("DEBUG!")
            else:
                elem = elem[0]

            if dim.elem_type == "select":
                try:
                    option_elem = elem.select_one("[selected]")
                    selected_id = get_option_value(option_elem)
                    selected_label = get_option_text(option_elem)
                except AttributeError:
                    option_elem = elem.select_one("option")
                    selected_id = get_option_value(option_elem)
                    selected_label = get_option_text(option_elem)

                selected_cat = selected_id
            elif dim.elem_type == "radio":
                selected_cat, selected_label = None, None
                # [('0', 'Somatik', True), ('1', 'Psykiatri', False)]
                for (_id, label, checked) in parse_radio_inputs(elem):
                    if checked:
                        selected_cat = _id
                        selected_label = label

                assert selected_cat is not None
                assert selected_label is not None

            elif dim.elem_type == "checkbox":
                selected_cat = elem.has_attr("checked")
                selected_label = selected_cat

            current_selection[dim.id] = (selected_cat, selected_label)

        return current_selection

class VantetiderDimension(Dimension):
    """docstring for VantetiderDimension"""

    @property
    def elem_type(self):
        """ :returns: "select"|"radio"|"checkbox"
        """
        if not hasattr(self, "_elem_type"):
            self._elem_type = get_elem_type(self.elem)
        return self._elem_type


    @property
    def default_value(self):
        """ The default category when making a query
        """
        if not hasattr(self, "_default_value"):
            if self.elem_type == "select":
                try:
                    # Get option marked "selected"
                    def_value = get_option_value(self.elem.select_one("[selected]"))
                except AttributeError:
                    # ...or if that one doesen't exist get the first option
                    def_value = get_option_value(self.elem.select_one("option"))


            elif self.elem_type == "checkbox":
                def_value = self.elem.get("value")

            elif self.elem_type == "radio":
                def_value = [x for x in self.elem if x.has_attr("checked")][0].get("value")

            self._default_value = def_value

            assert def_value is not None

        return self._default_value

class PrintLogger():
    """ Empyt "fake" logger
    """

    def log(self, msg, *args, **kwargs):
        print msg

    def debug(self, msg, *args, **kwargs):
        print msg

    def info(self, msg, *args, **kwargs):
        print msg

    def warning(self, msg, *args, **kwargs):
        print msg

    def error(self, msg, *args, **kwargs):
        print msg

    def critical(self, msg, *args, **kwargs):
        print msg


# UTILS
class Datatable(object):
    def __init__(self, html):
        self.soup = BeautifulSoup(html, 'html.parser')
        self.data = self._parse_values()
        self._measures = None
        # Assumption: the data table is the last table on the page


    @property
    def has_tabs(self):
        """ Does the table have tabs?
            Like http://www.vantetider.se/Kontaktkort/Sveriges/VantatKortareAn60Dagar/
        """
        return len(self.soup.select(".table_switch")) > 0

    @property
    def has_horizontal_scroll(self):
        """ Does the table have horizontal scroll?
            Like http://www.vantetider.se/Kontaktkort/Sveriges/VantatKortareAn60Dagar/
        """
        return len(self.soup.select(".DTFC_ScrollWrapper")) > 0

    @property
    def has_vertical_scroll(self):
        """ Does the table have vertical scroll?
            Like http://www.vantetider.se/Kontaktkort/Sveriges/PrimarvardTelefon/
        """
        return bool(self.soup.select_one("#DataTables_Table_0_wrapper"))



    @property
    def measures(self):
        """ Get a list of the measuers of this datatable
            Measures can be "Antal Besök inom 7 dagar",
            "Måluppfyllelse vårdgarantin", etc
        """
        if self._measures == None:
            self._measures = get_unique([x["measure"] for x in self.data])

        return self._measures

    def _parse_values(self):
        """ Get values
        """
        data = []
        if self.has_tabs:
            def _parse_tab_text(tab):
                # Annoying html in tabs
                if tab.select_one(".visible_normal"):
                    return tab.select_one(".visible_normal").text
                else:
                    return tab.text

            sub_table_ids = [_parse_tab_text(x) for x in self.soup.select(".table_switch li")]
            sub_tables = self.soup.select(".dataTables_wrapper")
            assert len(sub_tables) == len(sub_table_ids)
            assert len(sub_tables) > 0

            for measure, table in zip(sub_table_ids, sub_tables):
                if self.has_horizontal_scroll:
                    _data = self._parse_horizontal_scroll_table(table)
                    for region, col, value in _data:
                        data.append({
                            "region_or_unit": region,
                            "select_period": col, # Hardcode warning!
                            "measure": measure,
                            })

        else:
            if self.has_horizontal_scroll:
                raise NotImplementedError()

            if self.has_vertical_scroll:
                table = self.soup.select_one("#DataTables_Table_0_wrapper")
                _data = self._parse_vertical_scroll_table(table)
            else:
                table = self.soup.select(".chart.table.scrolling")[-1]
                _data = self._parse_regular_table(table)

            for region, measure, value in _data:
                data.append({
                    "region_or_unit": region,
                    "measure": measure,
                    "value": value
                })

        return data

    def _parse_horizontal_scroll_table(self, table_html):
        """ Get list of dicts from horizontally scrollable table
        """
        row_labels = [parse_text(x.text) for x  in table_html.select(".DTFC_LeftBodyWrapper tbody tr")]
        row_label_ids = [None] * len(row_labels)
        cols = [parse_text(x.text) for x in table_html.select(".dataTables_scrollHead th")]
        value_rows = table_html.select(".dataTables_scrollBody tbody tr")

        values = []
        for row_i, value_row in enumerate(value_rows):
            row_values = [parse_value(x.text) for x in value_row.select("td")]
            values.append(row_values)

        sheet = Sheet(zip(row_label_ids, row_labels), cols, values)

        return sheet.long_format

    def _parse_vertical_scroll_table(self, table_html):
        value_rows = table_html.select("tbody tr")
        row_labels = [parse_text(x.select_one("td").text) for x in value_rows]
        row_label_ids = [None] * len(row_labels)
        if table_html.select_one("td .clickable"):
            row_label_ids = [parse_landsting(x.select_one("td .clickable").get("onclick")) for x in value_rows]

        cols = [parse_text(x.text) for x in table_html.select(".dataTables_scrollHead th")][1:]
        values = []
        for row in value_rows:
            row_values = [ parse_value(x.text) for x in row.select("td")[1:] ]
            values.append(row_values)

        sheet = Sheet(zip(row_label_ids, row_labels), cols, values)

        return sheet.long_format

    def _parse_regular_table(self, table_html):
        value_rows = table_html.select("tbody tr")
        row_labels = [parse_text(x.select_one("td").text) for x in value_rows]
        row_label_ids = [None] * len(row_labels)
        if table_html.select_one("td .clickable"):
            row_label_ids = [parse_landsting(x.select_one("td .clickable").get("onclick")) for x in value_rows]
        cols = [parse_text(x.text) for x in table_html.select("th")][1:]
        values = []
        for row in value_rows:
            row_values = [ parse_value(x.text) for x in row.select("td")[1:] ]
            values.append(row_values)

        sheet = Sheet(zip(row_label_ids, row_labels), cols, values)

        return sheet.long_format



class Sheet(object):
    """ Represents a two-dimensional sheet/table with data
    """
    def __init__(self, rows, cols, values):
        """
            :param rows: a list with row values
            :param cols: a list with column headers
            :param values: a list of lists with row values
        """
        self.values_by_row = values
        self.values = flatten(values)

        if len(rows) * len(cols) == len(self.values):
            msg = ("Error initing sheet. Factor of n rows ({})",
                "and cols ({}) don't add up. Got {}, expected {}."\
                .format(len(rows), len(cols), len(rows) * len(cols), len(self.values)))

        assert len(rows) == len(values)
        assert len(cols) == len(values[0])

        self.row_index = rows
        self.col_index = cols

    @property
    def as_dictlist(self):
        """ Returns a dictlist with values
            [
                {
                    "row": "row_a",
                    "col": "col_a",
                    "value": 1,
                }
            ]
        """
        data = []
        for row_i, row in enumerate(self.row_index):
            for col_i, col in enumerate(self.col_index):
                value = self.values_by_row[row_i][col_i]
                data.append({
                    "row": row,
                    "col": col,
                    "value": value,
                    })
        return data

    @property
    def long_format(self):
        return zip(
            repeat(self.row_index, len(self.col_index)),
            self.col_index * len(self.row_index),
            self.values
            )

def get_unique(l):
    """ Get unique values from list
        Placed outside the class beacuse `list` conflicts our internal
        method with the same name.
    """
    return list(set(l))

def get_elem_type(elem):
    """ Get elem type of soup selection
        :param elem: a soup element
    """
    elem_type = None
    if isinstance(elem, list):
        if elem[0].get("type") == "radio":
            elem_type = "radio"
        else:
            raise ValueError(u"Unknown element type: {}".format(elem))

    elif elem.name == "select":
        elem_type = "select"

    elif elem.name == "input":
        elem_type = elem.get("type")

    else:
        raise ValueError(u"Unknown element type: {}".format(elem))

    # To be removed
    assert elem_type is not None

    return elem_type

def get_option_value(elem):
    """ Get the value attribute, or if it doesn't exist the text
        content.
        <option value="foo">bar</option> => "foo"
        <option>bar</option> => "bar"
        :param elem: a soup element
    """
    value = elem.get("value")
    if value is None:
        value = elem.text.strip()
    if value is None or value == "":
        msg = u"Error parsing value from {}.".format(elem)
        raise ValueError(msg)

    return value

def get_option_text(elem):
    """ Get the text of option
        <option value="foo">bar</option> => "bar"
        <option>bar</option> => "bar"
        :param elem: a soup element
    """
    return elem.text.strip()

def parse_radio_inputs(elem):
    """Get label and value of a radio inputs.
    >>> parse_radio_inputs('<input type="radio" value="1" id="Somatik" checked="checked"/>')
    #  [
        ("1", "Somatik", True)
        ]
    """
    data = []
    _values = []

    # Hack: Due to malformated html we have to parse input
    # tags with regex
    input_tags = re.findall(r'<input[^>]*>', str(elem))
    for input_tag in input_tags:
        value = re.findall(r'value="(\w+)"', input_tag)[0]
        _id = re.findall(r'id="(\w+)"', input_tag)[0]
        checked = "checked" in input_tag
        if value not in _values:
            data.append((value, _id, checked))
            # Again, malformated html makes some input appear twice
            _values.append(value)
    return data


def parse_value(val):
    """ Parse values from html
    """
    val = val.replace("%", " ")\
        .replace(" ","")\
        .replace(",", ".")\
        .replace("st","").strip()

    missing = ["Ejdeltagit", "N/A", "-"]
    if val in missing:
        return val
    elif val == "":
        return None

    return float(val)

def parse_text(val):
    """ Format strings fetched from html
    """
    return val.replace("\n", " ").strip()

def parse_landsting(val):
    """ Get region/unit id from "handle_click_event_landsting(this, 1)"
    """
    try:
        return re.search("\(this, (\d+)", val).group(1)
    except AttributeError:
        return None

def is_string(val):
    return isinstance(val, str) or isinstance(val, unicode)

def flatten(l):
    """Flatten list of lists
    """
    return [item for sublist in l for item in sublist]

def repeat(l, n):
    """ Repeat all items in list n times
        repeat([1,2,3], 2) => [1,1,2,2,3,3]
        http://stackoverflow.com/questions/24225072/repeating-elements-of-a-list-n-times
    """
    return [x for x in l for i in range(n)]

def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def guess_measure_unit(values):
    last_words = [x.split(" ")[-1] for x in values]
    counts = Counter(last_words).most_common()
    max_share = float(counts[0][1] / float(len(values)) )
    if max_share <= 0.5:
        raise ParseError(u"Not sure how to interpret the measure unit in: {}".format(values))

    return counts[0][0]
