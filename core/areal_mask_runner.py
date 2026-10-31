"""@brief Command-line runner for generating and verifying 4320x2160 WGS84 Equirectangular areal masks for IHS."""

import argparse
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
  sys.path.insert(0, _REPO_ROOT)

from core.ArealMaskPipeline import ArealMaskPipeline


def buildArgumentParser ():
  """
  @brief Construct CLI argument parser for the BR Mitchell areal mask pipeline.
  @return Configured argparse.ArgumentParser instance.
  """
  parser = argparse.ArgumentParser(
    description="Generate 4320x2160 WGS84 Equirectangular PNG areal masks and JSON RGB registries for all IHS locations."
  )
  parser.add_argument("--locale", type=str, default="en_gb", choices=["en_gb", "fr", "de"], help="CLI message locale.")

  #Return statement
  return parser


def runArealMaskCli (arg1_argv_array=None):
  """
  @brief Parse CLI arguments, execute ArealMaskPipeline, and exit non-zero if any location is unaccounted.
  @param arg1_argv_array Optional CLI argument list.
  @return Summary dictionary from ArealMaskPipeline.E_runFullPipeline.
  """
  #Convert from parameters
  argv_array = arg1_argv_array

  #Declare local instance variables
  args = None
  parser = None
  pipeline = None
  summary_obj = {}

  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

  parser = buildArgumentParser()
  args = parser.parse_args(argv_array)
  pipeline = ArealMaskPipeline(_REPO_ROOT, {"locale": args.locale})
  summary_obj = pipeline.E_runFullPipeline()

  if len(summary_obj.get("unaccounted_locations", [])) > 0:
    sys.stderr.write(f"Console error: {len(summary_obj['unaccounted_locations'])} locations unaccounted!\n")
    sys.exit(1)

  #Return statement
  return summary_obj


if __name__ == "__main__":
  runArealMaskCli()

