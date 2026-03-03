/**
 * Factory function to create normalizer functions based on a schema template
 * Handles type conversion and default values for nested objects
 */
function createNormalizer(schema) {
  return function normalize(source) {
    const src = source || {};
    const result = {};

    for (const [key, template] of Object.entries(schema)) {
      // Handle nested objects recursively
      if (typeof template === 'object' && template !== null && !Array.isArray(template)) {
        result[key] = createNormalizer(template)(src[key]);
      }
      // Handle boolean values
      else if (typeof template === 'boolean') {
        result[key] = Boolean(src[key]);
      }
      // Handle string values (including string defaults like '0')
      else if (typeof template === 'string') {
        result[key] = String(src[key] ?? template);
      }
      // Handle other primitive values
      else {
        result[key] = src[key] ?? template;
      }
    }
    return result;
  };
}

/**
 * Schema defining the structure and default values for spell entries
 */
const spellSchema = {
  name: '',
  level: '0',
  attack_save: '',
  casting_time: '',
  range: '',
  components: '',
  duration: '',
  notes: '',
  bonus_action: false,
  crrm: {
    concentration: false,
    ritual: false,
  },
};

/**
 * Schema defining the structure and default values for attack entries
 */
const attackSchema = {
  name: '',
  atk_bonus_or_dc: '',
  damage_and_type: '',
  notes: '',
  bonus_action: false,
};

/**
 * Character Editor utilities for Alpine.js
 * Provides normalizer functions for spell and attack entries
 */
window.CharacterEditor = {
  /**
   * Normalizer function for spell entries
   * Ensures consistent data structure and type conversion
   */
  normalizeSpell: createNormalizer(spellSchema),

  /**
   * Normalizer function for attack entries
   * Ensures consistent data structure and type conversion
   */
  normalizeAttack: createNormalizer(attackSchema),
};

