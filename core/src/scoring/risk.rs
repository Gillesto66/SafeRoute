// Fait par Gillesto
// risk.rs — Calcul du score de risque par segment via KDE (Kernel Density Estimation)
//
// Référence : Galbrun et al., "Safe Navigation in Urban Environments", KDD 2015
//
// Principe : chaque crime est un point (lat, lon, weight).
// Pour un segment de route, on calcule la densité de crimes dans son voisinage
// via un noyau gaussien. Le score est normalisé dans [0, 1].

use serde::{Deserialize, Serialize};

/// Un événement criminel géolocalisé
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrimeEvent {
    pub lat: f64,
    pub lon: f64,
    pub weight: f64, // gravité : 1.0 = délit mineur, 3.0 = crime violent
}

/// Calcule le score KDE pour un point (lat, lon) donné
/// en fonction d'une liste d'événements criminels.
///
/// # Arguments
/// * `point_lat`, `point_lon` — coordonnées du segment à scorer
/// * `crimes` — liste des événements criminels
/// * `bandwidth_m` — rayon du noyau en mètres (typiquement 200-500m)
pub fn kde_risk_score(
    point_lat: f64,
    point_lon: f64,
    crimes: &[CrimeEvent],
    bandwidth_m: f64,
) -> f64 {
    if crimes.is_empty() {
        return 0.0;
    }

    let h2 = bandwidth_m * bandwidth_m;
    let score: f64 = crimes
        .iter()
        .map(|crime| {
            let dist = haversine_m(point_lat, point_lon, crime.lat, crime.lon);
            // Noyau gaussien : K(d) = exp(-d²/2h²)
            let kernel = (-dist * dist / (2.0 * h2)).exp();
            kernel * crime.weight
        })
        .sum();

    score
}

/// Normalise un vecteur de scores dans [0, 1]
pub fn normalize_scores(scores: &mut Vec<f64>) {
    let max = scores.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    if max > 0.0 {
        scores.iter_mut().for_each(|s| *s /= max);
    }
}

/// Distance haversine en mètres entre deux points GPS
fn haversine_m(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let dlat = (lat2 - lat1).to_radians();
    let dlon = (lon2 - lon1).to_radians();
    let a = (dlat / 2.0).sin().powi(2)
        + lat1.to_radians().cos() * lat2.to_radians().cos() * (dlon / 2.0).sin().powi(2);
    6_371_000.0 * 2.0 * a.sqrt().atan2((1.0 - a).sqrt())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kde_no_crimes() {
        let score = kde_risk_score(51.5, -0.1, &[], 300.0);
        assert_eq!(score, 0.0);
    }

    #[test]
    fn test_kde_crime_at_same_point() {
        let crimes = vec![CrimeEvent { lat: 51.5, lon: -0.1, weight: 1.0 }];
        let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
        // Distance = 0 → kernel = exp(0) = 1.0 → score = 1.0
        assert!((score - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_kde_crime_far_away() {
        // Crime à ~10km → score très faible avec bandwidth=300m
        let crimes = vec![CrimeEvent { lat: 51.6, lon: -0.1, weight: 1.0 }];
        let score = kde_risk_score(51.5, -0.1, &crimes, 300.0);
        assert!(score < 0.001);
    }

    #[test]
    fn test_normalize() {
        let mut scores = vec![0.0, 5.0, 10.0, 2.5];
        normalize_scores(&mut scores);
        assert!((scores[2] - 1.0).abs() < 1e-9);
        assert!((scores[1] - 0.5).abs() < 1e-9);
    }
}
