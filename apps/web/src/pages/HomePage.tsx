import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/context";

interface Health {
  status: string;
}

export function HomePage() {
  const api = useApi();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.get<Health>("/healthz", signal),
    retry: false,
  });

  return (
    <section className="page">
      <h1>Your collection, priced by the market.</h1>
      <p className="lede">
        Track every card you own, see what it sells for, and spot which players are moving.
      </p>
      <p className="status" data-testid="api-status">
        <span
          className={`status__dot status__dot--${health.isSuccess ? "ok" : health.isError ? "down" : "pending"}`}
          aria-hidden="true"
        />
        {health.isPending ? "Checking API…" : health.isSuccess ? "API online" : "API unavailable"}
      </p>
    </section>
  );
}
