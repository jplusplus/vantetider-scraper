# encoding: utf-8
from unittest import TestCase

from vantetider import VantetiderScraper
from requests.exceptions import HTTPError


class TestVantetider(TestCase):

    def setUp(self):
        self.scraper = VantetiderScraper()

    def test_fetch_all_datasets(self):
        """Setting up scraper."""
        self.assertTrue(len(self.scraper.items))

    def test_get_regions(self):
        for dataset in self.scraper.items:
            regions = dataset.regions
            self.assertTrue(regions["27"].label == "Blekinge")
            self.assertTrue(regions.get_by_label("Blekinge") == "27")

            self.assertTrue(regions.get_by_label("foo") is None)


    def test_get_years(self):
        for dataset in self.scraper.items:
            if "year" in dataset.dimensions:
                years = dataset.dimensions["year"].allowed_values
                self.assertTrue(len(years) > 0)

    def test_latest_timepoint(self):
        dataset = self.scraper.get("Overbelaggning")

        latest_timepoint = dataset.latest_timepoint
        self.assertTrue(isinstance(latest_timepoint, dict))
        self.assertTrue("year" in latest_timepoint)


    def test_get_radio_values(self):
        dataset = self.scraper.get("Overbelaggning")
        values = dataset.dimensions["type_of_overbelaggning"].allowed_values
        self.assertTrue(len(values) == 2)

    def test_fetch_dataset(self):
        u"""Moving to an “API”."""
        self.scraper.get("PrimarvardBesok")

        #self.assertTrue(isinstance(dataset, Dataset))

        self.assertTrue(len(self.scraper.items) > 0)


    def test_fetch_dimensions(self):
        u"""Make sure that ALL datasets has dimensions"""
        for dataset in self.scraper.items:
            self.assertGreater(len(dataset.dimensions), 0)

    def test_basic_query(self):
        """Make a basic query to all implemeted datasets."""
        for dataset in self.scraper.items:
            res = dataset.fetch({"region": ["Blekinge"]})
            df = res.pandas
            self.assertGreater(df.shape[0], 0)




    def test_multi_period_query(self):
        """ Query multiple periods and years at once
        """
        dataset = self.scraper.get("Overbelaggning")
        res = dataset.fetch({
            "region": ["Gotland"],
            "year": ["2017", "2016"],
            "period": ["Januari", "Februari"],
            })
        df = res.pandas
        self.assertGreater(df.shape[0],0)
        self.assertEqual(len(df.year.unique()),2)
        self.assertEqual(len(df.period.unique()),2)
