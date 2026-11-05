import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { Dialog } from '../src/components/ui';

function Nested() {
  const [outer, setOuter] = useState(false), [inner, setInner] = useState(false);
  return <main><button onClick={() => setOuter(true)}>Abrir exterior</button>
    {outer && <Dialog title="Exterior" onClose={() => setOuter(false)}>
      <button onClick={() => setInner(true)}>Abrir interior</button>
      {inner && <Dialog title="Interior" onClose={() => setInner(false)}><input aria-label="Valor interior" /></Dialog>}
    </Dialog>}
  </main>;
}

test('Escape cierra solo el diálogo superior y restaura el foco y el fondo por nivel', async () => {
  const user = userEvent.setup();
  render(<Nested />);
  const initial = screen.getByRole('button', { name: 'Abrir exterior' });
  await user.click(initial);
  const outer = screen.getByRole('dialog', { name: 'Exterior' });
  const next = screen.getByRole('button', { name: 'Abrir interior' });
  await user.click(next);
  expect(outer.closest('[inert]')).not.toBeNull();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(next).toHaveFocus());
  expect(outer.closest('[inert]')).toBeNull();
  expect(screen.queryByRole('dialog', { name: 'Interior' })).not.toBeInTheDocument();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(initial).toHaveFocus());
  expect(initial.closest('[inert]')).toBeNull();
});

test('desmontar ambos niveles conserva el estado inerte anterior del documento', async () => {
  const user = userEvent.setup();
  const outside = document.createElement('button');
  outside.textContent = 'Elemento independiente';
  document.body.append(outside);
  try {
    const view = render(<Nested />);
    await user.click(screen.getByRole('button', { name: 'Abrir exterior' }));
    await user.click(screen.getByRole('button', { name: 'Abrir interior' }));
    view.unmount();
    await waitFor(() => expect(outside).not.toHaveAttribute('inert'));
    expect(outside).not.toHaveAttribute('aria-hidden');
    outside.focus();
    expect(outside).toHaveFocus();
  } finally { outside.remove(); }
});

test('guardado pendiente bloquea Escape, cierre y clic en el fondo', async () => {
  const user = userEvent.setup(), close = vi.fn();
  render(<Dialog title="Guardando" onClose={close} closeDisabled><p>Operación pendiente</p></Dialog>);
  expect(screen.getByRole('button', { name: 'Cerrar' })).toBeDisabled();
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('dialog').parentElement);
  expect(close).not.toHaveBeenCalled();
});
