"""@brief Command-line interface for running the reusable BR Mitchell CV table digitisation pipeline."""

import argparse
import os
import sys

# Ensure repository root is on sys.path when invoked directly
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
  sys.path.insert(0, _REPO_ROOT)

from core.TableDigitiserPipeline import TableDigitiserPipeline


def buildArgumentParser ():
  """
  @brief Construct CLI argument parser for single-PDF, single-volume, page-slice, or full-corpus digitisation.
  @return Configured argparse.ArgumentParser instance.
  """
  parser = argparse.ArgumentParser(
    description="Digitise graphical historical statistical tables from scanned PDFs into structured per-section JSON."
  )
  parser.add_argument("--volume", type=str, default=None, help="Configured volume_id (africa_asia_oceania, americas, europe).")
  parser.add_argument("--pdf", type=str, default=None, help="Path to any custom PDF file to digitise reusably.")
  parser.add_argument("--start-page", type=int, default=None, help="Optional 0-based inclusive start PDF page.")
  parser.add_argument("--end-page", type=int, default=None, help="Optional 0-based exclusive end PDF page.")
  parser.add_argument("--workers", type=int, default=None, help="Override number of parallel CPU CV worker processes.")
  parser.add_argument("--batch-size", type=int, default=None, help="Override page batch size per GPU OCR flush.")
  parser.add_argument("--arch", type=str, default=None, help="Override EasyOCR recognition network name (default: english_g2).")
  parser.add_argument("--locale", type=str, default="en_gb", choices=["en_gb", "fr", "de"], help="CLI message locale.")
  parser.add_argument("--no-manifest", action="store_true", help="Skip writing top-level output/json/manifest.json.")

  #Return statement
  return parser


def runCli (arg1_argv_array=None):
  """
  @brief Parse CLI arguments and execute TableDigitiserPipeline.
  @param arg1_argv_array Optional argument list (defaults to sys.argv[1:]).
  @return Pipeline execution summary dictionary.
  """
  #Convert from parameters
  argv_array = arg1_argv_array

  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

  parser = buildArgumentParser()
  args = parser.parse_args(argv_array)

  pipeline = TableDigitiserPipeline(
    _REPO_ROOT,
    {
      "architecture": args.arch,
      "locale": args.locale,
      "page_batch_size": args.batch_size,
      "workers": args.workers
    }
  )
  summary_obj = pipeline.D_runPipeline({
    "end_page": args.end_page,
    "pdf_path": args.pdf,
    "start_page": args.start_page,
    "volume_id": args.volume,
    "write_manifest": not args.no_manifest
  })

  #Return statement
  return summary_obj


if __name__ == "__main__":
  runCli()
