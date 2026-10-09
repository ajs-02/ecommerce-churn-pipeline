"""Generate nine raw and feature profiles from PostgreSQL after dbt build."""

import argparse
from profiling_analysis import generate_profiles
from upload_data import public_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()
    try:
        summary = generate_profiles(args.output_dir)
        print(
            f"Generated {len(summary['tables'])} profiles and data_profile_report.html"
        )
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(public_error(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
