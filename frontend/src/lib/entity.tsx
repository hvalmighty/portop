import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Entity } from "./types";

interface EntityState {
  entities: Entity[];
  entity: string; // "" = all entities
  setEntity: (e: string) => void;
  ccy: string;
}

const Ctx = createContext<EntityState | null>(null);
const KEY = "mpower.entity";

export function EntityProvider({ children }: { children: ReactNode }) {
  const { data = [] } = useQuery({ queryKey: ["entities"], queryFn: () => api<Entity[]>("/auth/entities"), staleTime: Infinity });
  const [entity, setEntityState] = useState<string>(() => localStorage.getItem(KEY) ?? "SG");
  useEffect(() => {
    if (data.length && entity && !data.some((e) => e.code === entity)) setEntityState(data[0].code);
  }, [data, entity]);
  const value = useMemo<EntityState>(
    () => ({
      entities: data,
      entity,
      setEntity: (e) => {
        localStorage.setItem(KEY, e);
        setEntityState(e);
      },
      ccy: data.find((e) => e.code === entity)?.reporting_ccy ?? "USD",
    }),
    [data, entity],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useEntity() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useEntity outside EntityProvider");
  return c;
}
