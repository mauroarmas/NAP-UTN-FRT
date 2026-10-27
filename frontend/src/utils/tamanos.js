export const recursosTamano = (size) => ({ vcpus: size.vcpus, ram_mb: size.ram_mb, disk_gb: size.disk_gb });
export const tamanosCompatibles = (sizes, minimum) => minimum ? sizes.filter((size) =>
  ['vcpus', 'ram_mb', 'disk_gb'].every((key) => Number.isInteger(minimum[key]) && size[key] >= minimum[key])) : [];
export const resumenRecursos = (size) => `${size.vcpus} vCPU · ${size.ram_mb} MB RAM · ${size.disk_gb} GB disco`;
