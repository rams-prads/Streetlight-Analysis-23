import { CaseType } from '../../../core/models/ptx.model';

export interface CaseTypeInfo {
  code: CaseType;
  label: string;
  labelTe: string;
  help: string;
  needsUpin: boolean;
  citizen: boolean;
}

/** Application types in plain words, so owners and counter staff pick the right one (ease of use). */
export const CASE_TYPES: CaseTypeInfo[] = [
  { code: 'SELF_ASSESSMENT', label: 'Self-assessment of a new building', labelTe: 'కొత్త భవనానికి స్వీయ మదింపు',
    help: 'You built or completed a building that has no property number yet. Enter its details; an inspector checks them.',
    needsUpin: false, citizen: true },
  { code: 'NEW_ASSESSMENT', label: 'New assessment (by GWMC)', labelTe: 'కొత్త మదింపు (జీడబ్ల్యూఎంసీ ద్వారా)',
    help: 'A building found without a property number, assessed by the revenue staff.', needsUpin: false, citizen: false },
  { code: 'MUTATION', label: 'Change of owner (mutation)', labelTe: 'యజమాని మార్పు (మ్యుటేషన్)',
    help: 'The property was sold, gifted, inherited, partitioned or changed by court order. Apply as the new owner.',
    needsUpin: true, citizen: true },
  { code: 'USE_CHANGE', label: 'Change of use', labelTe: 'వినియోగ మార్పు',
    help: 'A floor is now used differently, e.g. a house floor became a shop.', needsUpin: true, citizen: true },
  { code: 'REASSESSMENT', label: 'Addition or alteration (reassessment)', labelTe: 'అదనపు నిర్మాణం / మార్పు (పునర్మదింపు)',
    help: 'Floors were added, built-up area changed, or the recorded details are wrong.', needsUpin: true, citizen: true },
  { code: 'EXEMPTION', label: 'Exemption or concession', labelTe: 'మినహాయింపు లేదా రాయితీ',
    help: 'The property qualifies for a notified exemption (e.g. place of worship). A supporting document is needed.',
    needsUpin: true, citizen: true },
  { code: 'SUBDIVISION', label: 'Split one property into parts', labelTe: 'ఒక ఆస్తిని భాగాలుగా విభజన',
    help: 'One property becomes two or more, each with its own number and tax.', needsUpin: true, citizen: false },
  { code: 'BACK_ASSESSMENT', label: 'Correct earlier years (back-assessment)', labelTe: 'గత సంవత్సరాల సవరణ (బ్యాక్-అసెస్‌మెంట్)',
    help: 'A property was assessed too low, or not at all, in earlier years. The correct details are charged from the year they began; the Commissioner approves.',
    needsUpin: true, citizen: false },
  { code: 'DEMOLITION', label: 'Building demolished (close the property)', labelTe: 'భవనం కూల్చివేత (ఆస్తిని మూసివేయండి)',
    help: 'The whole building has been pulled down. Tax stops from that billing period and bills raised after it are reversed. For a part only, use "Addition or alteration" and remove the floors.',
    needsUpin: true, citizen: true },
  { code: 'APARTMENT', label: 'Apartment building (flats)', labelTe: 'అపార్ట్‌మెంట్ భవనం (ఫ్లాట్లు)',
    help: 'A building with several flats. Each flat gets its own property number and tax, with its share of the site and common areas.',
    needsUpin: false, citizen: false },
  { code: 'AMALGAMATION', label: 'Merge properties into one', labelTe: 'ఆస్తులను ఒకటిగా విలీనం',
    help: 'Two or more neighbouring properties in the same ward become one property number.', needsUpin: false, citizen: false },
];

export function caseTypeInfo(code: string): CaseTypeInfo | undefined {
  return CASE_TYPES.find((t) => t.code === code);
}
