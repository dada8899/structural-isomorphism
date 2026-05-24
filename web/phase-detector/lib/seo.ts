// W12-B (session #10, 2026-05-15): SEO helpers — site constants + structured
// data builders shared across pages.
//
// Why this lives in lib/ instead of inline in each page:
//   * Hostname / siteName / twitter handle drift fast; one constant table
//     means a single edit propagates everywhere.
//   * Structured-data builders are pure functions, easy to unit-test.
//   * Server components can import from here, so per-route layout.tsx
//     files stay slim.

import type { Metadata } from "next";

export const SITE_URL = "https://phase.bytedance.city";
export const SITE_NAME = "Phase Detector";
export const TWITTER_HANDLE = "@dada8899";
export const DEFAULT_OG_IMAGE = "/og/home.png";

/**
 * Build a Next.js Metadata object for a given page. Defaults stamp the
 * canonical URL + OG image + twitter card; callers override the page-
 * specific bits.
 */
export function buildMetadata(opts: {
  title: string;
  description: string;
  path: string;
  ogImage?: string;
  ogType?: "website" | "article" | "profile";
  noindex?: boolean;
}): Metadata {
  const url = `${SITE_URL}${opts.path.startsWith("/") ? opts.path : `/${opts.path}`}`;
  const image = opts.ogImage ?? DEFAULT_OG_IMAGE;
  return {
    title: opts.title,
    description: opts.description,
    alternates: { canonical: url },
    openGraph: {
      title: opts.title,
      description: opts.description,
      type: opts.ogType ?? "website",
      url,
      siteName: SITE_NAME,
      images: [
        {
          url: image,
          width: 1200,
          height: 630,
          alt: opts.title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: opts.title,
      description: opts.description,
      images: [image],
      creator: TWITTER_HANDLE,
    },
    robots: opts.noindex
      ? { index: false, follow: false }
      : { index: true, follow: true },
  };
}

// -------- JSON-LD schema builders --------

export function websiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: SITE_URL,
    description:
      "100 家全球上市公司的状态评分，用解释地震、银行挤兑的同一套数学。",
    inLanguage: "zh-CN",
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
    },
    potentialAction: {
      "@type": "SearchAction",
      target: `${SITE_URL}/companies?q={search_term_string}`,
      "query-input": "required name=search_term_string",
    },
  };
}

export function softwareApplicationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE_NAME,
    applicationCategory: "FinanceApplication",
    operatingSystem: "Web",
    url: SITE_URL,
    offers: [
      {
        "@type": "Offer",
        name: "Free",
        price: "0",
        priceCurrency: "USD",
      },
      {
        "@type": "Offer",
        name: "Pro",
        price: "19",
        priceCurrency: "USD",
      },
      {
        "@type": "Offer",
        name: "Team",
        price: "99",
        priceCurrency: "USD",
      },
    ],
  };
}

export function organizationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: SITE_URL,
    logo: `${SITE_URL}/og/home.png`,
    sameAs: [
      "https://github.com/dada8899/structural-isomorphism",
      "https://beta.structural.bytedance.city",
    ],
    founder: {
      "@type": "Person",
      name: "dada",
      url: "https://github.com/dada8899",
    },
  };
}

export function articleSchema(opts: {
  headline: string;
  description: string;
  url: string;
  datePublished: string;
  dateModified?: string;
  author?: string;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: opts.headline,
    description: opts.description,
    mainEntityOfPage: opts.url,
    url: opts.url,
    datePublished: opts.datePublished,
    dateModified: opts.dateModified ?? opts.datePublished,
    author: {
      "@type": "Organization",
      name: opts.author ?? SITE_NAME,
      url: SITE_URL,
    },
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
      logo: {
        "@type": "ImageObject",
        url: `${SITE_URL}/og/home.png`,
      },
    },
  };
}

export function definedTermSchema(opts: {
  id: string;
  name: string;
  description: string;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "DefinedTerm",
    "@id": `${SITE_URL}/universality/${opts.id}`,
    name: opts.name,
    description: opts.description,
    inDefinedTermSet: {
      "@type": "DefinedTermSet",
      name: "Phase Detector universality taxonomy",
      url: `${SITE_URL}/universality`,
    },
  };
}

export function datasetSchema(opts: {
  name: string;
  description: string;
  url: string;
  distributionUrl?: string;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: opts.name,
    description: opts.description,
    url: opts.url,
    license: "https://creativecommons.org/licenses/by/4.0/",
    creator: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
    },
    distribution: opts.distributionUrl
      ? {
          "@type": "DataDownload",
          encodingFormat: "application/json",
          contentUrl: opts.distributionUrl,
        }
      : undefined,
  };
}
