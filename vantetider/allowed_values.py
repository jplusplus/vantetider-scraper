# encoding: utf-8
"""A collection of allowed_values to make querying more convenient.
"""

# These are all available perdiods, but all are not available for all datasets
periods = [
    u"Våren",
    u"Hösten",
    u"Januari",
    u"Februari",
    u"Mars",
    u"April",
    u"Maj",
    u"Juni",
    u"Juli",
    u"Augusti",
    u"September",
    u"Oktober",
    u"November",
    u"December",
]

# Used by "Overbelaggning" dataset
type_of_overbelaggning = [
    # (id, label)
    ("0", "Somatik"),
    ("1", "Psykiatri"),
]
