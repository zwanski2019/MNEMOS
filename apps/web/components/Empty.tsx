import { Icon } from "@/components/Icon";

/**
 * What the console shows when the memory layer is unreachable.
 *
 * Deliberately not a spinner and definitely not placeholder numbers: an operator
 * looking at a recon dashboard has to be able to tell "nothing found" apart from
 * "we cannot see". Same reason the scope guard fails closed.
 */
export function MemoryUnavailable({ what }: { what: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
      <Icon name="gpp_bad" className="text-error text-2xl" />
      <p className="font-headline-md text-headline-md text-on-surface">
        Memory layer unreachable
      </p>
      <p className="font-data-mono text-data-mono text-on-surface-variant max-w-md">
        Could not read {what} from CockroachDB. Nothing is shown rather than
        something invented — this console never renders numbers it did not read.
      </p>
      <p className="font-data-mono text-[10px] text-outline mt-2">
        Set <span className="text-primary">WEB_DATABASE_URL</span> to a CockroachDB
        DSN and redeploy.
      </p>
    </div>
  );
}

/** Connected, queried successfully, and there is genuinely nothing there yet. */
export function NoRowsYet({ what, hint }: { what: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
      <Icon name="list_alt" className="text-outline text-2xl" />
      <p className="font-headline-md text-headline-md text-on-surface-variant">
        No {what} yet
      </p>
      <p className="font-data-mono text-data-mono text-outline max-w-md">
        {hint ?? "Run `make demo` to populate the memory layer."}
      </p>
    </div>
  );
}
