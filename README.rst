
This is a scraper for statistical data from http://www.vantetider.se built on top of the `Statscraper package <https://github.com/jplusplus/statscraper>`.

Install
-------

  pip install -r requirements.txt

The scraper has to do a lot of requests and uses `requests-cache <https://pypi.python.org/pypi/requests-cache>` to store queries.

Example usage
-------------

.. code:: python

  from vantetider import VantetiderScraper

  scraper = VantetiderScraper()
  scraper.items  # List _implemeted_ datasets
  # [<VantetiderDataset: VantatKortareAn60Dagar (Väntat kortare än 60 dagar )>, <VantetiderDataset: Overbelaggning (Överbeläggningar)>, <VantetiderDataset: PrimarvardTelefon (Telefontillgänglighet)>, <VantetiderDataset: PrimarvardBesok (Läkarbesök)>, <VantetiderDataset: SpecialiseradBesok (Förstabesök)>, <VantetiderDataset: SpecialiseradOperation (Operation/åtgärd)>]

  dataset = scraper.get("Overbelaggning")  # Get a specific dataset

  # List all available dimensions
  print dataset.dimensions

  print datatset.regions  # List available region
  print datatset.years  # List available years

  # Make a query, you have to explicitly define all dimension values you want
  # to query. By default the scraper will fetch default values.
  res = dataset.fetch({
    "region": "Blekinge",
    "year": "2016",
    "period": "Februari",
    # Currenty we can only query by id of dimension value
    "type_of_overbelaggning": ["0", "1"], # "Somatik" and "Psykiatri"
    })

  # Do something with the result
  df = res.pandas

Practical application, using dataset.py for storege.

.. code:: python

  from vantetider import VantetiderScraper
  from vantetider.allowed_values import TYPE_OF_OVERBELAGGNING, PERIODS
  import dataset

  db = dataset.connect('sqlite:///vantetider.db')

  TOPIC = "Overbelaggning"

  # Set up local db
  table = db.create_table(TOPIC)
  scraper = VantetiderScraper()

  dataset = scraper.get(TOPIC)

  # Get all available regions and years for query
  years = [x.value for x in dataset.years]
  regions = [x.value for x in dataset.regions]

  # Query in chunks to be able to store to database on the run
  for region in regions:
      for year in years:
          res = dataset.fetch({
              "year": year,
              "type_of_overbelaggning": [x[0] for x in TYPE_OF_OVERBELAGGNING],
              "period": PERIODS,
              "region": region,
              })
          df = res.pandas
          data = res.list_of_dicts
          table.insert_many(data)

TODO
----

- Implement scraping of "Aterbesok", "Undersokningar", "BUPdetalj", "BUP".
- Enable querying on label names on all dimensions
- Add more allowed values to `vantetider/allowed_values.py`
- Make requests-cache optional.

Devlop
------

Run tests:

  make tests
