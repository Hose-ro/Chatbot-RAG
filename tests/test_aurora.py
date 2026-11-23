import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        with self.assertRaises(rag.RespuestaModeloInvalida):
            self.consultar(
                self.otro_pdf, "¿Cuál es el presupuesto de Aurora?",
                '{"id": 0, "extracto": "47 pesos"}',
            )

    def test_respuesta_invalida_del_modelo(self):
        for salida in ("texto no JSON", "{}", '{"id": true, "extracto": "47 pesos"}'):
            with self.subTest(salida=salida), self.assertRaises(rag.RespuestaModeloInvalida):
                self.consultar(self.aurora, "¿Cuál es el presupuesto?", salida)


class PruebasIndice(unittest.TestCase):
    def setUp(self):
        self.pdf = crear_pdf("Presupuesto: 47 pesos.")
        self.document_id = rag.id_indice(self.pdf)
        conectar = patch("rag.conectar_supabase")
        generar = patch("rag.generar_embeddings", return_value=[[1.0] * 1024])
        self.conectar = conectar.start()
        self.addCleanup(conectar.stop)
        self.embeddings = generar.start()
        self.addCleanup(generar.stop)
        tabla = self.conectar.return_value.table
        self.indices = tabla.return_value
        self.fragmentos = Mock()
        tablas = {"document_indexes": self.indices, "document_chunks": self.fragmentos}
        tabla.side_effect = tablas.__getitem__
        self.indices.select.return_value.eq.return_value.execute.return_value.data = []

    def test_indice_existente_no_recalcula_vectores(self):
        self.indices.select.return_value.eq.return_value.execute.return_value.data = [
            {"chunk_count": 1},
        ]
        self.assertEqual(rag.preparar_pdf(self.pdf), rag.IndicePreparado(1, True))
        self.embeddings.assert_not_called()
        self.fragmentos.upsert.assert_not_called()

    def test_retry_registra_indice_solo_cuando_termina_la_escritura(self):
        escribir = self.fragmentos.upsert.return_value.execute
        escribir.side_effect = [RuntimeError("falló el lote"), None]
        with self.assertRaises(RuntimeError):
            rag.preparar_pdf(self.pdf)
        self.indices.upsert.assert_not_called()

        self.assertEqual(rag.preparar_pdf(self.pdf), rag.IndicePreparado(1, False))
        agregado = self.indices.upsert.call_args.args[0]
        self.assertEqual(agregado["document_id"], self.document_id)
        self.assertEqual(agregado["embedding_model"], rag.MODELO_EMBEDDING)
        self.assertEqual(agregado["chunk_count"], 1)
        self.assertTrue(self.fragmentos.upsert.call_args.kwargs["ignore_duplicates"])
