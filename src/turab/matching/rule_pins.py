"""Rule source pins (G4-2). Written by `db/dev/pin_rules.py`, which only adds.

A Python file rather than JSON, so the source fingerprint
(`db/dev/source_fingerprint.py`, which covers .py files) binds every test run
to the exact pins it ran with.
"""

FORMAT = 1

PINS: dict[str, str] = {
    'criterion.area_min@1': 'db0d9ebfe402214130b14e7f2488d976f01bc67919399bd1e79b3757b239bda9',
    'criterion.area_min@2': 'ee6876e0500ef4572a7501da31a397d9102135d55b1b49279e7831c457edc627',
    'criterion.attribute_option@1': 'e306194ca6f522c12913badde67f57720254222a848a4cd5db284d37dccec5e9',
    'criterion.attribute_option@2': 'a167db3d8ba5e80ac7bb506c17bf17def1cfbff99bb6e6205285b752e48513a8',
    'criterion.budget_max_sale@1': 'c9432c321827dde580bb149fda34aae607d563221a6bc64ca6f36e3e7e66a089',
    'criterion.count_min@1': 'e5d482d7d5378c3854d7f76eca0f66e8c2cc89a0e084a42140c9b90ff94a68d6',
    'criterion.count_min@2': 'a92c8d34ef56e19e6e5fd361c6ec94ad4f3f5628de611201bdc926a0492a2a46',
    'criterion.location@1': '12508fa37b0f43d12e63b539413856f14a40acd37b277f1e01e0b817bb8f0d6e',
    'criterion.location@2': 'd2533698c8e86802f28fc1c38041681deb5149e5c5039331acb1eb9c2c91257a',
    'criterion.no_deterministic_rule@1': '9a1ccd3eb39c8c1c6eeecb9cc45fd9cb1fbc4e29b7dfda66f3629c7a4c451be2',
    'criterion.property_type@1': 'a6f0b7c1ba2af9eadf4d5be065bb0a4e00afdf43d01389a1dc0b6b46dd698a7a',
    'criterion.transaction_intent@1': '5c3cff88be4d0f447f018d4571cec571dbbe1c36294f4a31af870dcc1ec4c4f0',
}
