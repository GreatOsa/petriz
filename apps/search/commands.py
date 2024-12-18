import sys
import typing
import csv
from pathlib import Path

from sqlalchemy.orm import Session

from helpers.fastapi.sqlalchemy.setup import get_session
from .models import Term
from core import commands


def csv_row_to_term(
    row: typing.Dict,
    source_name: typing.Optional[str] = None,
    verified: bool = False,
) -> Term:
    """Return a Term instance from a CSV row"""
    return Term(
        name=row["Term"],
        definition=row["Definition"],
        grammatical_label=row.get("Grammatical Label", None),
        topics=row.get("Topic", "").split(","),
        verified=verified,
        source_name=source_name,
        source_url=row.get("URL", None),
    )


def load_terms_from_csv_and_save_to_db(
    db_session: Session,
    csv_file: typing.Union[Path, str],
    data_source: typing.Optional[str] = None,
    batch_size: int = 1000,
) -> int:
    """
    Load petroleum terms from a CSV file and save them to the database

    :param db_session: The database session to use
    :param csv_file: Path to the CSV file containing the terms
    :param data_source: The name of the source of the data
    :param batch_size: The number of terms to commit to the database at once
    :return: The number of terms loaded to the database
    """
    path = Path(csv_file).resolve()
    term_count = 0
    last_committed_at = 0

    with open(path, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            term = csv_row_to_term(
                row,
                source_name=data_source,
                verified=True,
            )
            db_session.add(term)
            term_count += 1

            if (term_count - last_committed_at) >= batch_size:
                db_session.commit()
                last_committed_at = term_count

        db_session.commit()
    return term_count


@commands.register
def load_terms_to_db(
    csv_file: typing.Union[Path, str],
    data_source: typing.Optional[str] = None,
):
    """
    Load petroleum terms from a CSV file and save them to the database

    :param csv_file: Path to the CSV file containing the terms
    :param data_source: The name of the source of the data
    """
    db_session = next(get_session())
    term_count = load_terms_from_csv_and_save_to_db(
        db_session=db_session,
        csv_file=csv_file,
        batch_size=1000,
        data_source=data_source,
    )
    sys.stdout.write(f"Loaded {term_count} terms to the database\n")
    return None
