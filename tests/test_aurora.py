import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import rag
from documentos import extraer_fragmentos


def crear_pdf(*paginas: str) -> bytes:
    escritor = PdfWriter()
    for texto in paginas:
        hoja = escritor.add_blank_page(width=300, height=150)
        if not texto:
            continue
        hoja[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }),
            }),
        })
        contenido = DecodedStreamObject()
        contenido.set_data(f"BT /F1 10 Tf 10 100 Td ({texto}) Tj ET".encode("ascii"))
        hoja.replace_contents(contenido)

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


class PruebasAurora(unittest.TestCase):
    def setUp(self):
        self.aurora = extraer_fragmentos(
            crear_pdf("El presupuesto del proyecto Aurora es de 47 pesos.")
        )[0]
        self.otro_pdf = extraer_fragmentos(
            crear_pdf("El presupuesto del proyecto Aurora es de 99 pesos.")
        )[0]

    def consultar(self, fragmento, pregunta, salida_modelo):
        documentos = {
            fila["document_id"]: fila for fila in (self.aurora, self.otro_pdf)
        }
        vector = [1.0] + [0.0] * 1023
        respuesta = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=salida_modelo))]
        )
        with (
            patch("rag.conectar_supabase") as conectar,
            patch("rag.generar_embeddings", return_value=[vector]),
            patch.object(rag.ollama.chat.completions, "create", return_value=respuesta),
        ):
            rpc = conectar.return_value.rpc
            rpc.side_effect = lambda nombre, args: SimpleNamespace(
                execute=lambda: SimpleNamespace(
                    data=[documentos[args["target_document_id"]]]
                ),
            )
            resultado = rag.responder(fragmento["document_id"], pregunta)
            rpc.assert_called_once()
            nombre, args = rpc.call_args.args
            self.assertEqual(nombre, "match_document_chunks")
            self.assertEqual(args["target_document_id"], fragmento["document_id"])
            self.assertEqual(args["match_count"], 5)
            return resultado

    def test_presupuesto_con_cita(self):
        resultado = self.consultar(
            self.aurora, "¿Cuál es el presupuesto de Aurora?",
            '{"id": 0, "extracto": "47 pesos"}',
        )
        self.assertEqual(resultado.texto, "47 pesos [p. 1]")
        self.assertEqual(resultado.fuente, rag.Fuente(1, self.aurora["content"]))

    def test_aprobador_sin_evidencia(self):
        resultado = self.consultar(
            self.aurora, "¿Quién aprobó el presupuesto?",
            '{"id": null, "extracto": ""}',
        )
        self.assertEqual(resultado, rag.Respuesta(rag.SIN_EVIDENCIA))

    def test_portada_vacia_conserva_la_pagina(self):
        fragmentos = extraer_fragmentos(crear_pdf("", "Presupuesto: 47 pesos."))
        self.assertEqual([fila["page_number"] for fila in fragmentos], [2])
        self.assertIn("47 pesos", fragmentos[0]["content"])

    def test_pdf_completamente_vacio(self):
        with self.assertRaisesRegex(ValueError, "texto seleccionable"):
            extraer_fragmentos(crear_pdf("", ""))

    def test_consulta_aislada_al_pdf_activo(self):
        resultado = self.consultar(
            self.otro_pdf, "¿Cuál es el presupuesto de Aurora?",
            '{"id": 0, "extracto": "99 pesos"}',
        )
        self.assertEqual(resultado.texto, "99 pesos [p. 1]")
        self.assertEqual(resultado.fuente, rag.Fuente(1, self.otro_pdf["content"]))
        resultado = self.consultar(
            self.otro_pdf, "¿Cuál es el presupuesto de Aurora?",
            '{"id": 0, "extracto": "47 pesos"}',
        )
        self.assertEqual(resultado, rag.Respuesta(rag.SIN_EVIDENCIA))
