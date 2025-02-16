import sys
import typing
import csv
from pathlib import Path
from sqlalchemy.orm import Session

from helpers.fastapi.sqlalchemy.setup import get_session
from .models import Term, Topic
from core import commands


def get_topic_by_name_or_create_topic(
    db_session: Session,
    name: str,
    description: typing.Optional[str] = None,
) -> Topic:
    """
    Get a topic by name or create a new topic if it does not exist

    :param db_session: The database session to use
    :param name: The name of the topic
    :param description: The description of the topic
    :return: The topic
    """
    name = name.strip()
    topic = db_session.query(Topic).filter(Topic.name.ilike(name)).first()
    if topic:
        return topic

    topic = Topic(name=name, description=description)
    db_session.add(topic)
    db_session.flush()
    return topic


def get_term_by_name(db_session: Session, name: str) -> typing.Optional[Term]:
    """
    Get a term by name

    :param db_session: The database session to use
    :param name: The name of the term
    :return: The term
    """
    return db_session.query(Term).filter(Term.name.ilike(name.strip())).first()


def row_to_term(
    row: typing.Dict,
    source_name: typing.Optional[str] = None,
    verified: bool = False,
) -> Term:
    """Return a Term instance from a CSV row"""
    return Term(
        name=row["Term"],
        definition=row["Definition"],
        grammatical_label=row.get("Grammatical Label", None),
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
        reader = csv.DictReader(file, skipinitialspace=True)
        topic_cache = {}
        added_terms = set()
        for row in reader:
            if not row["Term"] or row["Term"] in added_terms:
                continue

            term = get_term_by_name(db_session, row["Term"])
            if not term:
                term = row_to_term(
                    row,
                    source_name=data_source,
                    verified=True,
                )
                db_session.add(term)
                term_count += 1
            added_terms.add(row["Term"])

            with db_session.begin_nested():
                for topic_name in row["Topic"].split(","):
                    if not topic_name:
                        continue

                    if topic_name in topic_cache:
                        topic = topic_cache[topic_name]
                    else:
                        topic = get_topic_by_name_or_create_topic(
                            db_session,
                            name=topic_name,
                        )
                    topic_cache[topic_name] = topic
                    term.topics.add(topic)

            if (term_count - last_committed_at) >= batch_size:
                db_session.commit()
                last_committed_at = term_count

        db_session.commit()
    return term_count


@commands.register
def load_terms(
    csv_file: typing.Union[Path, str],
    data_source: typing.Optional[str] = None,
):
    """
    Load petroleum terms from a CSV file and save them to the database

    :param csv_file: Path to the CSV file containing the terms
    :param data_source: The name of the source of the data
    """
    with get_session() as db_session:
        try:
            term_count = load_terms_from_csv_and_save_to_db(
                db_session=db_session,
                csv_file=csv_file,
                batch_size=1000,
                data_source=data_source,
            )
        except Exception:
            db_session.rollback()
            raise

    sys.stdout.write(f"Loaded {term_count} new terms to the database\n")
    return None
