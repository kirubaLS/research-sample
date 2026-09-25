"use client";

/**
 * Option lists for the real 6-step /attend/onboarding wizard. Recreated from the
 * mock-era file deleted in commit 8cd13db (it was dead code then, nothing used it --
 * this wizard now does), plus careersKnownOptions/futureConcernOptions: the reference
 * design's Future Plans step does ask both ("Which careers or exams have you heard
 * about?" and "Is there anything that may affect your future study choice?"), each
 * backed by StudentProfile.careers_known/future_concern.
 */

import {
  Atom,
  Baby,
  Banknote,
  BookOpen,
  Briefcase,
  Building,
  Building2,
  Calculator,
  Cog,
  Compass,
  CircleHelp,
  Dumbbell,
  FlaskConical,
  Gavel,
  GraduationCap,
  HandHeart,
  Handshake,
  Hammer,
  HelpCircle,
  Home as HomeIcon,
  Landmark,
  Lightbulb,
  Map,
  MessagesSquare,
  Music,
  PawPrint,
  Palette,
  PenLine,
  PiggyBank,
  Puzzle,
  School,
  ScrollText,
  Shield,
  ShieldQuestion,
  Sprout,
  Stethoscope,
  Store,
  Trees,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export interface Option {
  id: string;
  label: string;
  icon: LucideIcon;
}

export function labelFor(options: Option[], id: string): string {
  return options.find((o) => o.id === id)?.label ?? "";
}

export function labelsFor(options: Option[], ids: string[]): string[] {
  return ids.map((id) => labelFor(options, id)).filter(Boolean);
}

// -------------------------------------------------------------------------
// Basic information
// -------------------------------------------------------------------------

export const genderOptions: Option[] = [
  { id: "male", label: "Male", icon: Users },
  { id: "female", label: "Female", icon: Users },
  { id: "prefer_not_to_say", label: "Prefer not to say", icon: ShieldQuestion },
];

// -------------------------------------------------------------------------
// Section 1, Your Background
// -------------------------------------------------------------------------

export const livesInOptions: Option[] = [
  { id: "village", label: "Village", icon: Trees },
  { id: "town", label: "Town", icon: Building },
  { id: "city", label: "City", icon: Building2 },
];

export const decisionHelperOptions: Option[] = [
  { id: "self", label: "I decide myself", icon: Compass },
  { id: "parents", label: "My parents decide", icon: HomeIcon },
  { id: "family", label: "Me and my family together", icon: Users },
  { id: "teacher", label: "Teacher/school helps me", icon: School },
  { id: "relative", label: "Relative helps me", icon: Handshake },
  { id: "unsure", label: "Not sure yet", icon: HelpCircle },
];

export const responsibilitiesOptions: Option[] = [
  { id: "yes", label: "Yes", icon: Baby },
  { id: "no", label: "No", icon: Shield },
  { id: "unsure", label: "Not sure yet", icon: HelpCircle },
];

// -------------------------------------------------------------------------
// Section 2, Your Learning Profile
// -------------------------------------------------------------------------

export const subjectOptions: Option[] = [
  { id: "Mathematics", label: "Mathematics", icon: Calculator },
  { id: "Science", label: "Science", icon: Atom },
  { id: "English", label: "English", icon: BookOpen },
  { id: "Social Science", label: "Social Science", icon: Users },
];

export const learningTypeOptions: Option[] = [
  { id: "solving", label: "Solving problems and finding answers", icon: Puzzle },
  { id: "how_things_work", label: "Understanding how things work", icon: Cog },
  { id: "reading_sharing", label: "Reading, explaining and sharing ideas", icon: MessagesSquare },
  { id: "creating", label: "Creating or designing things", icon: Palette },
  { id: "numbers", label: "Working with numbers and information", icon: Calculator },
  { id: "unsure", label: "Not sure yet", icon: HelpCircle },
];

// -------------------------------------------------------------------------
// Section 3, Your Interests
// -------------------------------------------------------------------------

export const interestOptions: Option[] = [
  { id: "tech", label: "Computers and technology", icon: Cog },
  { id: "building", label: "Building or fixing things", icon: Wrench },
  { id: "creative", label: "Drawing/design/creative work", icon: Palette },
  { id: "sports", label: "Sports", icon: Dumbbell },
  { id: "music_dance", label: "Music/dance", icon: Music },
  { id: "reading_writing", label: "Reading/writing", icon: PenLine },
  { id: "helping", label: "Helping people", icon: HandHeart },
  { id: "nature", label: "Nature/animals", icon: PawPrint },
  { id: "business", label: "Business/selling activities", icon: Store },
];

export const workInterestOptions: Option[] = [
  { id: "people", label: "Working with people", icon: Users },
  { id: "machines", label: "Working with machines and technology", icon: Wrench },
  { id: "ideas", label: "Solving problems and finding ideas", icon: Lightbulb },
  { id: "numbers_money", label: "Working with numbers and money", icon: Banknote },
  { id: "creating_new", label: "Creating new things", icon: Sprout },
  { id: "unsure", label: "Not sure yet", icon: HelpCircle },
];

export const newLearningOptions: Option[] = [
  { id: "why", label: "Understanding why something happens", icon: Lightbulb },
  { id: "practical", label: "Doing practical activities", icon: Hammer },
  { id: "discussing", label: "Discussing with others", icon: MessagesSquare },
  { id: "experiments", label: "Trying experiments", icon: FlaskConical },
  { id: "facts", label: "Learning facts and information", icon: ScrollText },
  { id: "unsure", label: "Not sure yet", icon: HelpCircle },
];

// -------------------------------------------------------------------------
// Section 4, Your Future Plans
// -------------------------------------------------------------------------

export const class11GroupOptions: Option[] = [
  { id: "maths_bio", label: "Maths + Biology", icon: Calculator },
  { id: "maths_cs", label: "Maths + Computer Science", icon: Cog },
  { id: "bio_no_maths", label: "Biology without Maths", icon: FlaskConical },
  { id: "commerce", label: "Commerce", icon: Briefcase },
  { id: "arts", label: "Arts / Humanities", icon: Palette },
  { id: "vocational", label: "Vocational", icon: Wrench },
  { id: "diploma_iti", label: "Diploma / ITI", icon: GraduationCap },
  { id: "not_decided", label: "Not decided yet", icon: HelpCircle },
];

export const groupReasonOptions: Option[] = [
  { id: "like_subjects", label: "I like these subjects", icon: BookOpen },
  { id: "do_well", label: "I think I can do well in these subjects", icon: GraduationCap },
  { id: "career_match", label: "It matches my career interest", icon: Briefcase },
  { id: "parents_suggested", label: "My parents suggested it", icon: HomeIcon },
  { id: "friends_choosing", label: "My friends are choosing it", icon: Users },
  { id: "keeps_options_open", label: "It keeps many options open", icon: Compass },
  { id: "available_option", label: "It is the available option", icon: School },
  { id: "dont_know", label: "I don't know yet", icon: HelpCircle },
];

export const confidenceOptions: Option[] = [
  { id: "1", label: "1, Not sure at all", icon: HelpCircle },
  { id: "2", label: "2", icon: HelpCircle },
  { id: "3", label: "3, Still exploring", icon: Compass },
  { id: "4", label: "4", icon: Compass },
  { id: "5", label: "5, Completely sure", icon: GraduationCap },
];

export const careersKnownOptions: Option[] = [
  { id: "doctor", label: "Doctor / Healthcare", icon: Stethoscope },
  { id: "engineering", label: "Engineering / Technology", icon: Cog },
  { id: "ca_finance", label: "CA / Finance", icon: PiggyBank },
  { id: "law", label: "Law", icon: Gavel },
  { id: "defence", label: "Defence", icon: Shield },
  { id: "teaching", label: "Teaching", icon: School },
  { id: "design", label: "Design", icon: Palette },
  { id: "business", label: "Business", icon: Briefcase },
  { id: "government", label: "Government jobs", icon: Landmark },
  { id: "research", label: "Research", icon: FlaskConical },
  { id: "none", label: "None of these", icon: HelpCircle },
];

export const futureConcernOptions: Option[] = [
  { id: "cost", label: "College cost", icon: Banknote },
  { id: "close_home", label: "Staying close to home", icon: HomeIcon },
  { id: "moving_city", label: "Moving to another city", icon: Map },
  { id: "family", label: "Family responsibilities", icon: Users },
  { id: "not_thought", label: "I have not thought about this yet", icon: CircleHelp },
];
