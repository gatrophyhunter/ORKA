// Database schema. Values are stored in the units their sources publish (inches, grains, psi, bar)
// and converted to SI only at the engine boundary. Every record carries its sources.

export type SourceType = 'manufacturer' | 'standard' | 'government' | 'peer-reviewed' | 'third-party' | 'search-snippet' | 'user' | 'derived';

export interface Source {
  url: string;
  type: SourceType | string;
  fields?: string[];
  /** Page number inside a PDF document, when applicable. */
  page?: number | string | null;
  /** Date the document was retrieved (ISO). */
  retrieved?: string;
}

export interface Conflict {
  field: string;
  values: { value: unknown; source: string }[];
}

export interface CapacityEntry {
  value: number;
  brand: string | null;
  basis: string;
  source: string | null;
}

export interface Cartridge {
  id: string;
  name: string;
  aliases: string[];
  type: 'rifle' | 'handgun';
  standards: string[];
  bulletDiameterIn: number | null;
  boreDiameterIn: number | null;
  grooveDiameterIn: number | null;
  caseLengthMaxIn: number | null;
  trimLengthIn: number | null;
  maxCoalIn: number | null;
  saamiMapPsi: number | null;
  saamiMapCup: number | null;
  cipPmaxBar: number | null;
  saamiTwist: string | null;
  primerSize: string | null;
  caseCapacityGrH2O: CapacityEntry[];
  sources: Source[];
  conflicts?: Conflict[];
  notes?: string;
  user?: boolean;
}

export type PowderForm = 'spherical' | 'extruded' | 'flake' | 'disc' | null;

export interface BurnRateChartRank {
  chart: string;
  rank: number;
  chartUrl?: string;
}

export type ModelStatus = 'calibrated' | 'user-calibrated' | 'estimated' | 'none';

export interface PowderModelParams {
  forceJg: number;
  flameTempK: number;
  gamma: number;
  covolumeCm3g: number;
  solidDensityGcc: number;
  beta: number;
  n: number;
  lambda: number;
  mu: number;
  tempCoeffPerK: number;
  refTempC: number;
  /** Heat-loss multiplier fitted along with the powder (1 = model default). */
  heatScale?: number;
}

export interface PowderModelEntry {
  status: ModelStatus;
  params: PowderModelParams;
  /** Plain-language account of where the parameters came from. */
  derivation: string;
  /** For estimates: 1-sigma relative uncertainty of beta implied by the estimation method. */
  betaRelSigma?: number;
  calibration?: {
    points: number;
    rmsVelocityFps: number | null;
    rmsPressurePct: number | null;
    /** Cartridge ids the data came from. */
    cartridges: string[];
    sources: string[];
    /** Charge range covered by the calibration data, grains (predictions outside it are extrapolations). */
    chargeRangeGr?: [number, number];
    /** Fit quality from the RMS pressure error: good ≤ 10 %, fair ≤ 20 %, poor > 20 %. */
    grade?: 'good' | 'fair' | 'poor' | 'unvalidated';
    /** Median absolute held-out pressure error for this powder (leave-one-cartridge-out), percent, when measured. */
    heldOutPressurePct?: number | null;
  };
}

export interface Powder {
  id: string;
  manufacturer: string;
  brand?: string | null;
  name: string;
  form: PowderForm;
  base: 'single' | 'double' | 'triple' | null;
  nitroglycerinPct?: number | null;
  applications: string[];
  temperatureStableClaim?: string | null;
  bulkDensityGcc?: number | null;
  heatOfExplosionJg?: number | null;
  burnRateCharts: BurnRateChartRank[];
  status: 'current' | 'discontinued' | 'unknown';
  sources: Source[];
  notes?: string;
  model?: PowderModelEntry;
  user?: boolean;
}

export interface BurnRateChart {
  publisher: string;
  edition: string;
  url: string;
  /** Powder ids in chart order (fastest first); entries that could not be matched are "name:<as printed>". */
  orderedPowderIds: string[];
  /** Names exactly as printed on the chart, fastest first. */
  orderedNames?: string[];
}

export interface Bullet {
  id: string;
  manufacturer: string;
  line: string;
  name: string;
  sku?: string | null;
  caliberLabel?: string | null;
  diameterIn: number;
  weightGr: number;
  lengthIn: number | null;
  bcG1: number | null;
  bcG7: number | null;
  bcNotes?: string | null;
  profile?: string | null;
  tip?: string | null;
  construction?: string | null;
  recommendedTwist?: string | null;
  /** Boat-tail length (excluding heel), when the maker publishes it. Null = flat base or unknown. */
  boatTailLengthIn?: number | null;
  baseToOgiveIn?: number | null;
  status: 'current' | 'discontinued' | 'unknown';
  sources: Source[];
  notes?: string;
  user?: boolean;
}

export interface BrassBrand {
  id: string;
  name: string;
  country?: string | null;
  parent?: string | null;
  productLines?: string[];
  notes?: string;
  sources: Source[];
}

export interface BrassCase {
  brandId: string;
  cartridge: string;
  /** Normalised cartridge id, when it could be matched. */
  cartridgeId?: string | null;
  sku?: string | null;
  caseWeightGr?: number | null;
  waterCapacityGrH2O?: number | null;
  capacityCondition?: 'new' | 'fired' | 'unknown';
  primerSize?: string | null;
  primerPocketType?: string | null;
  basis?: string;
  sources: Source[];
  notes?: string;
  user?: boolean;
}

export interface ValidationLoad {
  cartridge: string;
  cartridgeId?: string | null;
  bulletMfr: string;
  bulletModel: string;
  bulletWeightGr: number;
  bulletDiameterIn?: number | null;
  bulletLengthIn?: number | null;
  caseBrand?: string | null;
  caseTrimLengthIn?: number | null;
  primer?: string | null;
  coalIn: number;
  barrelLengthIn: number;
  twist?: string | null;
  powder: string;
  powderId?: string | null;
  powderMfr?: string | null;
  chargeGr: number;
  velocityFps: number;
  pressure: number | null;
  pressureUnit: 'psi' | 'CUP' | 'bar' | null;
  pressureMethod?: string;
  loadType?: string;
  compressed?: boolean | null;
  sources: Source[];
  notes?: string;
}

export interface Database {
  version: string;
  generated: string;
  cartridges: Cartridge[];
  powders: Powder[];
  burnRateCharts: BurnRateChart[];
  bullets: Bullet[];
  brassBrands: BrassBrand[];
  brassCases: BrassCase[];
  validationLoads: ValidationLoad[];
}
