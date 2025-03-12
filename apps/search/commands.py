import typing
import csv
import click
from pathlib import Path
from urllib3.util.url import parse_url
from sqlalchemy.orm import Session

from helpers.fastapi import commands
from helpers.fastapi.sqlalchemy.setup import get_session
from .models import Term, Topic, TermSource


def get_or_create_topic_by_name(
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


def get_or_create_term_source_by_name(
    db_session: Session,
    name: str,
    description: typing.Optional[str] = None,
    url: typing.Optional[str] = None,
) -> TermSource:
    """
    Get a term source by name or create a new term source if it does not exist

    :param db_session: The database session to use
    :param name: The name of the term source
    :param description: The description of the term source
    :param url: The URL of the term source
    :return: The term source
    """
    name = name.strip()
    term_source = (
        db_session.query(TermSource).filter(TermSource.name.ilike(name)).first()
    )
    if term_source:
        return term_source

    term_source = TermSource(name=name, description=description, url=url)
    db_session.add(term_source)
    db_session.flush()
    return term_source


def row_to_term(
    db_session: Session,
    row: typing.Dict,
    source_name: typing.Optional[str] = None,
    verified: bool = False,
) -> Term:
    """Return a Term instance from a CSV row"""
    term_url = row.get("URL", None)
    if term_url:
        try:
            parsed_url = parse_url(term_url)
            source_url = parsed_url.scheme + "://" + parsed_url.netloc
        except Exception:
            source_url = None
    else:
        source_url = None
    term_source = get_or_create_term_source_by_name(
        db_session=db_session,
        name=source_name,
        url=source_url,
    )
    return Term(
        name=row["Term"],
        definition=row["Definition"],
        grammatical_label=row.get("Grammatical Label", None),
        verified=verified,
        source=term_source,
    )


def load_terms_from_csv_and_save_to_db(
    db_session: Session,
    csv_file: Path,
    data_source: typing.Optional[str] = None,
    batch_size: int = 1000,
) -> int:
    """Load petroleum terms from a CSV file and save them to the database."""
    term_count = 0
    last_committed_at = 0

    with open(csv_file, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file, skipinitialspace=True)
        if not {"Term", "Definition", "Topic"}.issubset(reader.fieldnames or []):
            raise click.BadParameter(
                "CSV file must contain 'Term', 'Definition', and 'Topic' columns"
            )

        topic_cache = {}
        added_terms = set()
        with click.progressbar(
            reader,
            label=f"Loading terms from {csv_file}",
            item_show_func=lambda r: r["Term"] if r else None,
        ) as rows:
            for row in rows:
                if not row["Term"] or row["Term"] in added_terms:
                    continue

                term = get_term_by_name(db_session, row["Term"])
                if not term:
                    term = row_to_term(
                        db_session,
                        row=row,
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

                        topic = topic_cache.get(
                            topic_name
                        ) or get_or_create_topic_by_name(db_session, name=topic_name)
                        topic_cache[topic_name] = topic
                        term.topics.add(topic)

                if (term_count - last_committed_at) >= batch_size:
                    db_session.commit()
                    last_committed_at = term_count

            db_session.commit()
    return term_count


@commands.register("load_terms")
@click.argument(
    "csv_file", type=click.Path(exists=True, path_type=Path, dir_okay=False)
)
@click.option(
    "--source",
    "-s",
    "data_source",
    help="Name of the data source",
)
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=1000,
    help="Number of terms to commit at once",
)
def load_terms(
    csv_file: Path,
    data_source: typing.Optional[str] = None,
    batch_size: int = 1000,
):
    """Load petroleum terms from a CSV file into the database."""
    try:
        with get_session() as db_session:
            term_count = load_terms_from_csv_and_save_to_db(
                db_session=db_session,
                csv_file=csv_file,
                batch_size=batch_size,
                data_source=data_source,
            )
        click.echo(
            click.style(f"\nSuccessfully loaded {term_count} new terms", fg="green")
        )
    except Exception as exc:
        click.echo(
            click.style(f"\nError loading terms: {str(exc)}", fg="red"), err=True
        )
        raise click.Abort()


__all__ = ["load_terms"]
