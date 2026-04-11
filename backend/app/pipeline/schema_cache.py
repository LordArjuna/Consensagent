import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    comment: str = ""


@dataclass
class TableMeta:
    database: str
    schema: str
    name: str
    columns: list = field(default_factory=list)
    comment: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.name}"

    def to_ddl(self) -> str:
        col_defs = ", ".join(
            f"{c.name} {c.data_type}" for c in self.columns
        )
        return f"{self.full_name} ({col_defs})"

    def to_description(self) -> str:
        col_parts = []
        for c in self.columns:
            desc = f"{c.name} ({c.data_type})"
            if c.comment:
                desc += f" -- {c.comment}"
            col_parts.append(desc)
        cols_str = ", ".join(col_parts)
        base = f"Table {self.full_name}: columns [{cols_str}]"
        if self.comment:
            base += f". Description: {self.comment}"
        return base


class SchemaCache:
    def __init__(self):
        self._tables: list = []
        self._descriptions: list = []
        self._embeddings: Optional[np.ndarray] = None
        self._built = False

    def build(self, snowflake_service, embedding_service) -> None:
        try:
            self._tables = self._introspect(snowflake_service)
            if not self._tables:
                logger.warning("SchemaCache: no tables discovered")
                return

            self._descriptions = [t.to_description() for t in self._tables]
            self._embeddings = embedding_service.encode(self._descriptions)
            self._built = True
            logger.info(f"SchemaCache built: {len(self._tables)} tables indexed")
        except Exception as e:
            logger.error(f"SchemaCache build failed: {e}")

    def _introspect(self, snowflake_service) -> list:
        tables = []
        try:
            raw_tables = snowflake_service.execute("SHOW TABLES IN DATABASE")
        except Exception as e:
            logger.error(f"Failed to list tables: {e}")
            return tables

        for row in raw_tables:
            table_name = row.get("name", "")
            schema_name = row.get("schema_name", "PUBLIC")
            db_name = row.get("database_name", "")
            comment = row.get("comment", "") or ""

            if not table_name:
                continue

            columns = self._get_columns(snowflake_service, db_name, schema_name, table_name)
            tables.append(TableMeta(
                database=db_name,
                schema=schema_name,
                name=table_name,
                columns=columns,
                comment=comment,
            ))

        return tables

    def _get_columns(self, snowflake_service, db: str, schema: str, table: str) -> list:
        columns = []
        try:
            raw_cols = snowflake_service.execute(
                f'SHOW COLUMNS IN TABLE "{db}"."{schema}"."{table}"'
            )
            for col in raw_cols:
                columns.append(ColumnMeta(
                    name=col.get("column_name", ""),
                    data_type=col.get("data_type", "VARIANT"),
                    comment=col.get("comment", "") or "",
                ))
        except Exception as e:
            logger.warning(f"Failed to get columns for {db}.{schema}.{table}: {e}")
        return columns

    @property
    def is_built(self) -> bool:
        return self._built

    def get_all_tables(self) -> list:
        return self._tables

    def get_descriptions(self) -> list:
        return self._descriptions

    def get_embeddings(self) -> Optional[np.ndarray]:
        return self._embeddings

    def get_table_by_name(self, name: str) -> Optional[TableMeta]:
        name_upper = name.upper()
        for t in self._tables:
            if t.name.upper() == name_upper or t.full_name.upper() == name_upper:
                return t
        return None

    def get_full_schema_ddl(self) -> str:
        return "\n".join(t.to_ddl() for t in self._tables)
