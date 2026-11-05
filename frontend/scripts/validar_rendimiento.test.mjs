import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarize } from './validar_rendimiento.mjs';

const rows=(failures,fastFailure=false)=>Array.from({length:100},(_,i)=>({flow:'metricas',warmup:false,
  valid:i>=failures,duration_ms:i<failures&&!fastFailure?30000:1000}));

test('p95 nearest-rank y tasa cuentan todos los errores y excluyen sólo calentamiento',()=>{
  let report=summarize([...rows(5),{flow:'metricas',warmup:true,valid:false,duration_ms:30000}]).metricas;
  assert.equal(report.samples,100);assert.equal(report.p95_ms,1000);assert.equal(report.valid_within_3s_ratio,.95);assert.equal(report.passed,true);
  report=summarize(rows(6)).metricas;
  assert.equal(report.p95_ms,30000);assert.equal(report.passed,false);
  report=summarize(rows(100,true)).metricas;
  assert.equal(report.p95_ms,1000);assert.equal(report.valid_within_3s_ratio,0);assert.equal(report.passed,false);
});

test('cada recorrido exige cien muestras propias, sin compensación entre flujos',()=>{
  const report=summarize([...rows(0),...rows(0).map(r=>({...r,flow:'pedidos'}))]);
  assert.equal(report.metricas.passed,true);assert.equal(report.pedidos.passed,true);
  assert.equal(report.servicios.passed,false);
  assert.equal(summarize(rows(0).slice(1)).metricas.passed,false);
});
