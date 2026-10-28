"""Contratos independientes del proveedor para la interpretación previa al RAG."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

TextoFiltro = Annotated[str, StringConstraints(strict=True, min_length=1)]
CantidadTokens = Annotated[int, Field(strict=True, ge=0)]


class ConsultaPreRag(BaseModel):
    """Los cinco campos que debe interpretar cualquier proveedor LLM."""

    model_config = ConfigDict(extra="forbid", strict=True)

    carrera: TextoFiltro | None
    nivel_educativo: TextoFiltro | None
    institucion: TextoFiltro | None
    ubicacion: TextoFiltro | None
    modalidad: TextoFiltro | None


class ConsumoTokens(BaseModel):
    """Conteos del proveedor; los desgloses no informados se representan con None."""

    model_config = ConfigDict(extra="forbid", strict=True)

    entrada: CantidadTokens
    salida: CantidadTokens
    total: CantidadTokens
    entrada_cache: CantidadTokens | None
    razonamiento: CantidadTokens | None


class RespuestaPreRag(ConsultaPreRag):
    """Salida común: filtros interpretados más consumo real informado por la API."""

    consumo_tokens: ConsumoTokens


class DatosOferta(BaseModel):
    """Los siete campos originales que recibe cualquier LLM para redactar."""

    model_config = ConfigDict(extra="forbid", strict=True)

    titulo: TextoFiltro = Field(alias="Título")
    lugar: TextoFiltro = Field(alias="Lugar donde se cursa")
    nivel: TextoFiltro = Field(alias="Nivel")
    descripcion: TextoFiltro = Field(alias="Descripción")
    modalidad: TextoFiltro = Field(alias="Tipo de cursada")
    gestion: TextoFiltro = Field(alias="Pública/Privada")
    url: TextoFiltro = Field(alias="URL")


class OfertaRecuperada(BaseModel):
    """Oferta de entrada independiente de Qdrant y del proveedor de LLM."""

    model_config = ConfigDict(extra="forbid", strict=True)

    original: DatosOferta


class RespuestaUsuario(BaseModel):
    """Texto para el usuario y consumo, común a los futuros adaptadores de LLM."""

    model_config = ConfigDict(extra="forbid", strict=True)

    respuesta: TextoFiltro
    consumo_tokens: ConsumoTokens
