def test_worker_solo_notificaciones_no_registra_trabajos_de_infraestructura(monkeypatch):
    from app import worker
    registered = []
    monkeypatch.setattr(worker.scheduler, 'registrar', lambda name, *args, **kwargs: registered.append(name))
    worker.registrar_trabajos(solo_notificaciones=True)
    assert registered == ['procesar_notificaciones']
