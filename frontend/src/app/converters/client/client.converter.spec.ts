import { displayName, sexLabel, toClient, toClients, versionLabel } from './client.converter';

describe('client converter', () => {
  it('fills defaults for a partial payload', () => {
    const c = toClient({ id: 'c1', full_name: 'Nora Ficticia Demo', sex: 'F', restrictions: ['contains_lactose'] });
    expect(c.id).toBe('c1');
    expect(c.age).toBeNull();
    expect(c.age_bucket).toBe('edad_NA');
    expect(c.has_allergies).toBeFalse();
    expect(c.diet_count).toBe(0);
    expect(c.restrictions).toEqual(['contains_lactose']);
  });

  it('converts lists, labels the sex and shows names, never keys (S9)', () => {
    expect(toClients([{ id: 'a' }, { id: 'b' }]).length).toBe(2);
    expect(sexLabel('M')).toBe('Hombre');
    expect(sexLabel(null)).toBe('—');
    expect(displayName({ full_name: '  Teo Ficticio Demo ' })).toBe('Teo Ficticio Demo');
    expect(displayName({ full_name: null })).toBe('Cliente sin nombre');
    expect(versionLabel('3012543d-5c31-4c8b-86d9-104169920f39::e02')).toBe('e02');
    expect(versionLabel(null)).toBe('');
  });
});
