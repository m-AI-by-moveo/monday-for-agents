import cron, { type ScheduledTask } from "node-cron";
import type {
  ScheduledJobContext,
  ScheduledJobDefinition,
  ScheduledJobResult,
  JobStatus,
} from "../scheduler/types.js";

// ---------------------------------------------------------------------------
// Scheduler service
// ---------------------------------------------------------------------------

export interface SchedulerService {
  /** Register a job definition to be scheduled */
  register(job: ScheduledJobDefinition): void;
  /** Start all registered (and enabled) jobs */
  startAll(timezone: string): void;
  /** Stop all running jobs */
  stopAll(): void;
  /** Get status of all registered jobs */
  getStatus(): JobStatus[];
}

interface ManagedJob {
  definition: ScheduledJobDefinition;
  task: ScheduledTask | null;
  running: boolean;
  lastRun: Date | null;
  lastResult: ScheduledJobResult | null;
  consecutiveFailures: number;
}

export function createSchedulerService(
  ctx: ScheduledJobContext,
): SchedulerService {
  const jobs = new Map<string, ManagedJob>();

  function register(definition: ScheduledJobDefinition): void {
    jobs.set(definition.id, {
      definition,
      task: null,
      running: false,
      lastRun: null,
      lastResult: null,
      consecutiveFailures: 0,
    });
  }

  function startAll(timezone: string): void {
    for (const [id, job] of jobs) {
      if (!job.definition.enabled) {
        console.log(`[scheduler] Skipping disabled job: ${job.definition.name}`);
        continue;
      }

      const task = cron.schedule(
        job.definition.cron,
        async () => {
          if (job.running) {
            console.log(
              `[scheduler] Skipping ${job.definition.name} — previous run still in progress`,
            );
            return;
          }

          job.running = true;
          const start = Date.now();
          console.log(`[scheduler] Running ${job.definition.name}...`);

          try {
            const result = await job.definition.execute(ctx);
            job.lastResult = result;
            job.lastRun = new Date();

            if (result.success) {
              job.consecutiveFailures = 0;
              const elapsed = Date.now() - start;
              console.log(
                `[scheduler] ${job.definition.name} completed in ${elapsed}ms (posted=${result.posted})`,
              );
            } else {
              job.consecutiveFailures++;
              console.error(
                `[scheduler] ${job.definition.name} failed: ${result.error} (failures=${job.consecutiveFailures})`,
              );
            }
          } catch (err) {
            job.consecutiveFailures++;
            const errorMsg = err instanceof Error ? err.message : String(err);
            job.lastResult = {
              success: false,
              posted: false,
              error: errorMsg,
            };
            job.lastRun = new Date();
            console.error(
              `[scheduler] ${job.definition.name} threw: ${errorMsg} (failures=${job.consecutiveFailures})`,
            );
          } finally {
            job.running = false;
          }
        },
        { timezone },
      );

      job.task = task;
      console.log(
        `[scheduler] Scheduled ${job.definition.name} — cron="${job.definition.cron}" tz=${timezone}`,
      );
    }
  }

  function stopAll(): void {
    for (const [id, job] of jobs) {
      if (job.task) {
        job.task.stop();
        job.task = null;
        console.log(`[scheduler] Stopped ${job.definition.name}`);
      }
    }
  }

  function getStatus(): JobStatus[] {
    return Array.from(jobs.values()).map((job) => ({
      id: job.definition.id,
      name: job.definition.name,
      enabled: job.definition.enabled,
      cron: job.definition.cron,
      running: job.running,
      lastRun: job.lastRun,
      lastResult: job.lastResult,
      consecutiveFailures: job.consecutiveFailures,
    }));
  }

  return { register, startAll, stopAll, getStatus };
}
