/**
 * Ready-made teams for a new room.
 *
 * Most people who open a blank "New room" form do not yet know what a good
 * team looks like. A template fills in a goal they can edit and, when the room
 * is created, makes the agents and seats them, so the first run is one click
 * away. The agents are ordinary agents in the user's library afterwards; they
 * can change or remove them like any other.
 *
 * Tools are left at the default (web search, page reading, today's date),
 * which every template here needs.
 */

export interface TemplateAgent {
  name: string
  role: string
  system_prompt: string
}

export interface RoomTemplate {
  id: string
  title: string
  /** One line on the card. */
  summary: string
  roomName: string
  /** Written so the part to change is obvious. */
  objective: string
  agents: TemplateAgent[]
}

export const roomTemplates: RoomTemplate[] = [
  {
    id: 'research-brief',
    title: 'Research brief',
    summary: 'A researcher finds recent facts with sources; a writer turns them into a one-page brief.',
    roomName: 'Research brief',
    objective:
      'Research the market for electric bikes in Europe in the last 12 months and write a one-page brief for a small business owner: the key numbers, the main trends, and three opportunities. Every fact must have a source link.',
    agents: [
      {
        name: 'Researcher',
        role: 'Finds recent, reliable facts with sources',
        system_prompt:
          'You are a careful researcher. Search the web for recent, reliable information on the topic you are given. Prefer official statistics, reputable news and industry reports from the last 12 months. For every fact, give the source name and link. Say clearly when sources disagree or when something could not be confirmed. Do not write the final brief; hand over organised notes.',
      },
      {
        name: 'Writer',
        role: 'Turns research notes into a clear one-page brief',
        system_prompt:
          "You are a clear business writer. Turn the researcher's notes into a one-page brief: a short summary first, then key numbers, trends and opportunities as short sections. Use plain words for a non-expert reader. Keep every source link next to the fact it supports. Do not add facts that are not in the notes.",
      },
    ],
  },
  {
    id: 'social-posts',
    title: 'Posts from an article',
    summary: 'Reads an article you link and writes ready-to-post LinkedIn and X posts from it.',
    roomName: 'Posts from an article',
    objective:
      'Read the article at https://example.com/your-article and write 3 LinkedIn posts and 3 X posts that share its main ideas. Friendly, professional tone; each post must make sense on its own.',
    agents: [
      {
        name: 'Reader',
        role: 'Reads the article and pulls out the key ideas',
        system_prompt:
          'You read web pages carefully. Open the article you are given and list its main ideas, the most quotable lines, and any numbers worth sharing, with the exact wording from the article. If the page cannot be opened, say so plainly instead of guessing what it says.',
      },
      {
        name: 'Copywriter',
        role: 'Writes social posts for LinkedIn and X',
        system_prompt:
          "You write social media posts. From the reader's notes, write the posts the goal asks for. LinkedIn posts: 80-150 words, a strong first line, short paragraphs, one question or call to action at the end. X posts: under 270 characters each. Never invent claims that are not in the notes. Number each post so the user can pick.",
      },
    ],
  },
  {
    id: 'competitor-check',
    title: 'Competitor check',
    summary: 'Compares a product with its main competitors on price, features and reviews.',
    roomName: 'Competitor check',
    objective:
      'Compare Notion with its three main competitors on price, main features and what users say in reviews. Give a comparison table and three practical recommendations for a small team choosing a tool.',
    agents: [
      {
        name: 'Market researcher',
        role: 'Collects prices, features and reviews for each product',
        system_prompt:
          "You research products. Identify the main competitors if they are not named, then collect each product's current prices, main features, and what users praise and complain about in reviews. Use the products' own pricing pages and well-known review sites, and give a link for every fact. Note the date of any price you find.",
      },
      {
        name: 'Analyst',
        role: 'Compares the options and gives recommendations',
        system_prompt:
          "You are a practical analyst. From the researcher's findings, build a comparison table (product, price, strengths, weaknesses) and write three recommendations for the reader described in the goal. Be specific about who each option suits. Keep the source links. Do not add facts that are not in the findings.",
      },
    ],
  },
]
