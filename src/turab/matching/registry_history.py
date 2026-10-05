"""Every rule-registry digest a stored match may cite (G4-19, decided (a) in
the review of c657bd9).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-2, G4-13, G4-19;
`docs/gate/evidence/REGISTRY-HISTORY.txt` (the git evidence for the entry
below).

## Why

G4-13 put `REGISTRY.digest()` into every match's input hash. G4-2 adds a
changed rule as a NEW version, so the digest changes whenever any version is
registered. To recompute an old match's hash, the digest it was evaluated
under must be known. From explanation format 2, each match records it
(`explanation.engine.registry_digest`).

## The historical entry

Matches written before that, explanation format 1, carry no digest.
- **Who wrote them.** Format 1 was written only by the code from `7a223d7`,
  which introduced the run, up to the commit that introduced format 2.
- **Under which registry.** In that whole range the registry did not change:
  `rule_pins.py`, `gates.py`, `rules.py` and `registry.py` are unchanged
  since `7a223d7` (`git log`, in the evidence file).
- **The attribution.** So every format-1 match was evaluated under ONE
  registry. This file pins that registry: its 20 pairs, each with its source
  sha256, and the digest they give.
- **How to check it.** The digest is reproducible from `rule_pins.py` at
  `7a223d7` alone, without running any code
  (`db/dev/registry_history_evidence.py`).

## The rules this file carries

- `FORMAT_DIGESTS[format]` names the digest of a format whose rows carry
  none. Only format 1 is listed. A row of any other format without a digest
  is NOT attributed: replay reports its hash as unproven, and never
  substitutes the current digest.
- `HISTORY` lists every registry a match can have been evaluated under. A
  new version is registered by adding an entry here in the same change, with
  its pairs. `test_the_current_registry_is_recorded_in_the_history` fails
  otherwise.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

#: Each entry: the digest, the commit from which it was the registry, and the
#: pairs (id, version, source sha256) it is the sha256 of, in registry order.
HISTORY = (
    {"digest": "7ddf47478a44a14aab4c81412da26ca200413ca9c5ad84ee86b21845b0b17298",
     "since": "7a223d7",
     "pairs": (
        ("action.next", "1", "76cb97622d5c3ba5808e42c074914e97a7efd9d33d8114fc8ad2526dee542d2a"),
        ("criterion.area_min", "1", "db0d9ebfe402214130b14e7f2488d976f01bc67919399bd1e79b3757b239bda9"),
        ("criterion.area_min", "2", "ee6876e0500ef4572a7501da31a397d9102135d55b1b49279e7831c457edc627"),
        ("criterion.attribute_option", "1", "e306194ca6f522c12913badde67f57720254222a848a4cd5db284d37dccec5e9"),
        ("criterion.attribute_option", "2", "a167db3d8ba5e80ac7bb506c17bf17def1cfbff99bb6e6205285b752e48513a8"),
        ("criterion.budget_max_sale", "1", "c9432c321827dde580bb149fda34aae607d563221a6bc64ca6f36e3e7e66a089"),
        ("criterion.count_min", "1", "e5d482d7d5378c3854d7f76eca0f66e8c2cc89a0e084a42140c9b90ff94a68d6"),
        ("criterion.count_min", "2", "a92c8d34ef56e19e6e5fd361c6ec94ad4f3f5628de611201bdc926a0492a2a46"),
        ("criterion.location", "1", "12508fa37b0f43d12e63b539413856f14a40acd37b277f1e01e0b817bb8f0d6e"),
        ("criterion.location", "2", "d2533698c8e86802f28fc1c38041681deb5149e5c5039331acb1eb9c2c91257a"),
        ("criterion.no_deterministic_rule", "1", "9a1ccd3eb39c8c1c6eeecb9cc45fd9cb1fbc4e29b7dfda66f3629c7a4c451be2"),
        ("criterion.property_type", "1", "a6f0b7c1ba2af9eadf4d5be065bb0a4e00afdf43d01389a1dc0b6b46dd698a7a"),
        ("criterion.transaction_intent", "1", "5c3cff88be4d0f447f018d4571cec571dbbe1c36294f4a31af870dcc1ec4c4f0"),
        ("eligibility.precedence", "1", "8ee5d2a7ff056988702dada7a0b3c6cb0e37ac629ac124826ca10d3b7f67f320"),
        ("freshness.gate", "1", "5a919b0976924dac98833eebce283acce4a532e1b915b2409e135a8445437d69"),
        ("freshness.state", "1", "4a9c5d0f8923f61c355b9aae1023661a6f816b578fd01bd887b2df5155066a72"),
        ("permission.binding_state", "1", "ce73e9484e4206c14d3eec82c1e02d7ea9cdaedd60692facd935dc02705ce415"),
        ("permission.gate", "1", "a15387909c35b23cbb165a8b438352024ff001b5ffce0e60714c65f7903ef61e"),
        ("score.soft", "1", "321c97ab9c290614539ae4a0524808065ba45835e30f791a0b8389a4eaf002c5"),
        ("score.soft", "2", "199e8a7e867d512774a1c27deea3ba823379c9770d741d0b8fb71931323dffb1"),
     )},
)

#: Rows of these explanation formats carry no digest; each was written under
#: exactly this one (see the module docstring).
FORMAT_DIGESTS = {
    "turab.match-explanation/1": "7ddf47478a44a14aab4c81412da26ca200413ca9c5ad84ee86b21845b0b17298",
}


def digest_of(pairs: Iterable[tuple[str, str, str]]) -> str:
    """The digest `RuleRegistry.digest` computes, from the pairs alone."""
    lines = "".join(f"{rule_id}\t{version}\t{source}\n"
                    for rule_id, version, source in sorted(pairs, key=lambda p: (p[0], p[1])))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def known(digest: str) -> bool:
    return any(entry["digest"] == digest for entry in HISTORY)
